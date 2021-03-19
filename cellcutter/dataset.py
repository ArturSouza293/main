import numpy as np
from numpy.random import default_rng
import tensorflow as tf

module_rng = default_rng()

class Dataset:

  def __init__(self, data_img, marker_img, label_img = None, crop_size = 64):
    if data_img.shape != marker_img.shape or (label_img is not None and data_img.shape != label_img.shape):
      raise ValueError('Image size not match each other')

    self.img = self.__normalize_img(data_img)
    self.marker_img = marker_img
    self.label_img = label_img
    self.crop_size = crop_size

    self.create_patches()

  def __normalize_img(self, img_in):
    img = img_in.astype(np.float32)
    if len(img.shape) == 2:
      img = img[..., np.newaxis]
    img -= np.min(img, axis = (0,1))
    img /= np.max(img, axis = (0,1))
    return img

  def __center_of_mass_as_int(self, img):
    d0, d1 = img.shape
    s = np.sum(img)
    c0 = int(np.sum(img, axis = 1).dot(np.arange(d0)) / s + .5)
    c1 = int(np.sum(img, axis = 0).dot(np.arange(d1)) / s + .5)
    return c0,c1

  def __is_within(self, coord, rect):
    return coord[0] >= rect[0] and coord[0] < rect[0] + rect[2] and coord[1] >= rect[1] and coord[1] < rect[1] + rect[3]

  def create_patches(self):
    d0,d1 = self.marker_img.shape
    indices = np.unique(self.marker_img)[1:]  #ignore 0

    self.patch_set = dict()
    for ind in indices:
      c0,c1 = np.round(self.__center_of_mass_as_int(self.marker_img == ind))
      c0 = sorted((0, c0 - self.crop_size // 2, d0 - self.crop_size))[1]
      c1 = sorted((0, c1 - self.crop_size // 2, d1 - self.crop_size))[1]

      data_patch_1 = self.img[c0:c0+self.crop_size,c1:c1+self.crop_size,:]
      data_patch_2 = self.marker_img[c0:c0+self.crop_size,c1:c1+self.crop_size] == ind
      data_patch = np.concatenate((data_patch_1, data_patch_2[...,np.newaxis]),axis = 2)

      if self.label_img is not None:
        label_patch = (self.label_img[c0:c0+self.crop_size,c1:c1+self.crop_size] == ind).astype(np.uint8)
        self.patch_set[ind] = ((c0,c1), data_patch, label_patch)
      else:
        self.patch_set[ind] = ((c0,c1), data_patch)

  def generator(self):
    '''
    A generator returning individual patches info: (coord, data, label) or (coord, data) if label_img is None
    '''
    for k in self.patch_set.keys():
        yield self.patch_set[k]

  def tf_dataset(self):
    d0,d1,ch = self.img.shape
    return tf.data.Dataset.from_generator(
      self.generator,
      output_signature = (
        tf.TensorSpec(shape=(2,), dtype=tf.int32),
        tf.TensorSpec(shape=(self.crop_size,self.crop_size, ch+1), dtype=tf.float32)
      ) if self.label_img is None else (
        tf.TensorSpec(shape=(2,), dtype=tf.int32),
        tf.TensorSpec(shape=(self.crop_size,self.crop_size, ch+1), dtype=tf.float32),
        tf.TensorSpec(shape=(self.crop_size,self.crop_size), dtype=tf.uint8)
      )
    )

  def generator_with_label(self):
    '''
    A generator returning individual patches pairs with label: (data, label)
    '''
    if self.label_img is None:
      raise ValueError('Lable Image not set.')

    for k in self.patch_set.keys():
      c, data, label = self.patch_set[k]
      yield (data, label)

  def tf_dataset_with_label(self):
    d0,d1,ch = self.img.shape
    return tf.data.Dataset.from_generator(
      self.generator_with_label,
      output_signature=(
        tf.TensorSpec(shape=(self.crop_size,self.crop_size,ch+1), dtype=tf.float32),
        tf.TensorSpec(shape=(self.crop_size,self.crop_size), dtype=tf.uint8)
      )
    )

  def generator_within_area(self, rng = None, area_size = 640):
    '''
    A generator returning all patches with a certain area, as well as the corresponding coordinates of all pathes
    '''
    if rng is None:
      rng = module_rng

    d0,d1 = self.marker_img.shape
    while True:
      a0 = rng.integers(d0 - area_size - self.crop_size)
      a1 = rng.integers(d1 - area_size - self.crop_size)

      all_indices = list(filter(
        lambda k: self.__is_within(self.patch_set[k][0], (a0, a1, area_size, area_size)),
        self.patch_set.keys()
      ))

      coords = [self.patch_set[k1][0] for k1 in all_indices]
      data = tf.stack([self.patch_set[k2][1] for k2 in all_indices])
      coords = np.array(coords) - np.array([a0,a1])
      yield data, coords