#! /usr/bin/env python
# coding=utf-8
#================================================================
#   Copyright (C) 2019 * Ltd. All rights reserved.
#
#   Editor      : VIM
#   File name   : image_demo.py
#   Author      : YunYang1994
#   Created date: 2019-07-12 13:07:27
#   Description :
#
#================================================================
import sys
import cv2
import numpy as np
import core.utils as utils
import tensorflow as tf
from core.yolov3 import YOLOv3, decode
from core.config import cfg
from PIL import Image

# Image to be processed
original_image      = cv2.imread(image_path) #you can and should replace this line to receive the image directly (not from a file)

# Read class names
class_names = {}
with open(cfg.YOLO.CLASSES, 'r') as data:
    for ID, name in enumerate(data):
        class_names[ID] = name.strip('\n')

# Setup tensorflow, keras and YOLOv3
input_size   = 416
input_layer  = tf.keras.layers.Input([input_size, input_size, 3])
feature_maps = YOLOv3(input_layer)

original_image      = cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB)
original_image_size = original_image.shape[:2]

image_data = utils.image_preporcess(np.copy(original_image), [input_size, input_size])
image_data = image_data[np.newaxis, ...].astype(np.float32)

bbox_tensors = []
for i, fm in enumerate(feature_maps):
    bbox_tensor = decode(fm, i)
    bbox_tensors.append(bbox_tensor)

model = tf.keras.Model(input_layer, bbox_tensors)
utils.load_weights(model, "./yolov3.weights")

pred_bbox = model.predict(image_data)
pred_bbox = [tf.reshape(x, (-1, tf.shape(x)[-1])) for x in pred_bbox]
pred_bbox = tf.concat(pred_bbox, axis=0)

bboxes = utils.postprocess_boxes(pred_bbox, original_image_size, input_size, 0.3)
bboxes = utils.nms(bboxes, 0.45, method='nms')

# We have our objects detected and boxed, lets move the class name into a list
objects_detected = []
for x0,y0,x1,y1,prob,class_id in bboxes:
    objects_detected.append(class_names[class_id])

'''# Lets show the user a nice picture - should be erased in production
image = utils.draw_bbox(original_image, bboxes)
image = Image.fromarray(image)
image.show()'''

print(f"Objects Detected: {objects_detected}")

