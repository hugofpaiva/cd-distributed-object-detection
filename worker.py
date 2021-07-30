import argparse
import random
import string
import requests
import tempfile
import io
import sys
import cv2
import numpy as np
import core.utils as utils
import tensorflow as tf
from core.yolov3 import YOLOv3, decode
from core.config import cfg
import json
import time, threading
from collections import Counter

WAIT_SECONDS = 25

# Setup tensorflow, keras and YOLOv3
input_size = 416
input_layer = tf.keras.layers.Input([input_size, input_size, 3])
feature_maps = YOLOv3(input_layer)

# Read class names
class_names = {}
with open(cfg.YOLO.CLASSES, 'r') as data:
    for ID, name in enumerate(data):
        class_names[ID] = name.strip('\n')

bbox_tensors = []
for i, fm in enumerate(feature_maps):
    bbox_tensor = decode(fm, i)
    bbox_tensors.append(bbox_tensor)

model = tf.keras.Model(input_layer, bbox_tensors)
utils.load_weights(model, "./yolov3.weights")
        
class Worker: 
    def __init__(self, server_address, server_port):
        self.server_address = server_address
        self.server_port = server_port
        self.register()
        self.keepAlive()
          
    
    @classmethod 
    # Função utilizada pelos workers para enviar e ir buscar informação ao servidor.
    def sendToServer(self, url, method, data=None):
        try:
            if method == 'GET':  
                r = requests.get(url)          
                
            elif method == 'POST':
                r=requests.post(url, data=data)
            r.raise_for_status()  # Raises a HTTPError if the status is 4xx, 5xxx
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            print ('\x1b[0;31;7m' + "Server down..." + '\x1b[0m') 
            sys.exit(1)
        except (requests.exceptions.HTTPError):
            text = r.text 
            print('\x1b[0;31;7m' +"Error: "+ text +'\x1b[0m')
            return r
        else:
            return r
    
    # Criação de um ID random, de length 8, para identificar de modo único cada worker
    def generateID(self):
        stringLength = 8
        lettersAndDigits = string.ascii_letters + string.digits
        return ''.join((random.choice(lettersAndDigits) for i in range(stringLength)))

    # Registo do worker no servidor
    def register(self):
        self.ID = self.generateID()
        self.url = "http://"+str(self.server_address) + ":"+str(self.server_port)+"/worker/" + str(self.ID)
        content = self.sendToServer(self.url, 'GET').text

        # Caso esse ID pertença a outro worker e já se encontre registado, este worker irá tentar registar-se novamente, gerando um novo ID.
        if content != "Worker registered!":
            self.register()
            
    # Função periódica que informa o servidor de que este worker ainda se encontra ativo.
    def keepAlive(self):
        self.sendToServer(self.url+"/alive", 'GET').text
        thrd = threading.Timer(WAIT_SECONDS, self.keepAlive)
        thrd.daemon = True
        thrd.start()


    # O worker irá aceder ao endpoint de requests, de onde, caso haja, irá buscar uma frame para processar. 
    # Caso lhe seja retornado false, significa que terá de se registar primeiro.  
    def run(self):
        while True:
            r = self.sendToServer(self.url+"/request", 'GET')
            content = r.content
            
            if content != b"No available work." and content != b"Worker not registered!":
                md5 = r.headers.get('content-disposition').split("filename=")
                md5 = md5[1].split("_")
                frame = md5[len(md5)-1].split(".")[0]
                md5 = md5[0]
                tmp = tempfile.NamedTemporaryFile()
                tmp = "".join([str(tmp.name), ".jpg"])
                
                open(tmp, "wb").write(content)
                tic = time.perf_counter()
                objects = self.compute(tmp)
                timeSpent = (time.perf_counter() - tic)*1000
    
                objects = Counter(objects)
                objects = json.dumps(objects)
                self.sendToServer(self.url+"/result", 'POST', data={'md5':md5, 'objects':objects, 'time': timeSpent, 'frame': frame})
                
                            
            elif content == b"Worker not registered!":
                self.register()
            
            else:
                time.sleep(2)

    # Função que o worker corre para gerar informação sobre a imagem.
    def compute(self, image):
        original_image = cv2.imread(image)

        original_image = cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB)
        original_image_size = original_image.shape[:2]

        image_data = utils.image_preporcess(np.copy(original_image), [input_size, input_size])
        image_data = image_data[np.newaxis, ...].astype(np.float32)

        pred_bbox = model.predict(image_data)
        pred_bbox = [tf.reshape(x, (-1, tf.shape(x)[-1])) for x in pred_bbox]
        pred_bbox = tf.concat(pred_bbox, axis=0)

        bboxes = utils.postprocess_boxes(
            pred_bbox, original_image_size, input_size, 0.3)
        bboxes = utils.nms(bboxes, 0.45, method='nms')

        objects_detected = []
        for x0, y0, x1, y1, prob, class_id in bboxes:
            objects_detected.append(class_names[class_id])
      
        return objects_detected


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-address",
                        help="server address", default="localhost")
    parser.add_argument(
        "--server-port", help="server address port", default=5000)
    args = parser.parse_args()
    
    w = Worker(args.server_address, args.server_port)

    w.run()

    
