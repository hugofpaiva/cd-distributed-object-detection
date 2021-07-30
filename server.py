from flask import Flask, redirect, url_for, render_template, request, send_file
import io
import os
import argparse
import redis
import json
import datetime
import time, threading
import sys
import tempfile
import hashlib
import cv2
from collections import Counter

app = Flask(__name__)

try:
    db = redis.Redis(host='localhost')
    db.flushdb()
except:
      print('\x1b[0;31;7m' +"Redis server not active!"+'\x1b[0m')
      sys.exit(1)

ALLOWED_EXTENSIONS = {'mp4', 'm4v'}
WAIT_SECONDS = 30

workersName = "workers"     # Nome do Redis-Set que guarda o nome de todos os workers ativos
videos = "video-frames"     # Nome da Redis-List que associa cada vídeo ao md5 correspondente.

# Verificação se o ficheiro tem as extensões permitidas previamente especificadas (.mp4 e .m4v)
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Endpoint de registo dos workers
@app.route('/worker/<name>')
def registerWorker(name):
    # Caso o worker já esteja registado no servidor, retorna falso 
    if db.sismember(workersName, name): 
        return 'Invalid registration, change name!', 400
    
    # Caso contrário, adiciona o nome do worker ao set acima definido, associando ao mesmo a hora de inscrição,
    # que será usada dentro de 30 segundos para verificar se o worker ainda se encontra ativo. Não lhe é logo atribuída uma frame.
    else: 
        db.sadd(workersName, name)
        data = {"heartbit": str(datetime.datetime.now()), "frame": ""}
        db.set(name, json.dumps(data))
        return 'Worker registered!' 

# Endpoint para os workers virem buscar frames para processar
@app.route('/worker/<name>/request')
def requestFrame(name):
    # Caso o worker não esteja registado no servidor
    if not db.sismember(workersName, name): 
        return 'Worker not registered!', 403
    
    md5Video = db.rpop(videos)
    
    if md5Video:
        frame = db.rpop(md5Video)
        # Atribuir frame ao worker e atualizar no set
        data = db.get(name)
        data = json.loads(data)
        # Caso contrário, ir-se-á dar update à hora associada ao worker, visto que existiu comunicação.
        alive(name)
        frameJson = json.loads(frame)

        data["frame"] = json.dumps(frameJson)
        db.set(name, json.dumps(data))
        
        if (db.llen(md5Video) > 0):
            # Voltar a colocar o video pela esquerda para ir rodando
            db.lpush(videos, md5Video) 

        return send_file(frameJson.get("file"), as_attachment=True)

    else:
        return "No available work."

# Endpoint para receber os resultados dos workers, assim que acabam de processar uma frame.
@app.route('/worker/<name>/result', methods=['POST'])
def results(name):
    # Caso o worker não esteja registado no servidor.
    if not db.sismember(workersName, name): 
        return 'Worker not registered!'
    
    dataWorker = db.get(name)
    dataWorker = json.loads(dataWorker)

    dataWorker["frame"] = None
    db.set(name, json.dumps(dataWorker))

    md5 = request.form.get('md5')
    objects = request.form.get('objects')
    frame = request.form.get('frame')
    time = float(request.form.get('time'))
    data = json.dumps({"name": name, "objects": objects, "md5": md5, "time": time, "frame": frame})
    db.lpush("results", data)
    return 'Result received!'

# Endpoint a partir do qual o servidor recebe confirmação dos workers que ainda estão ativos - um heartbit.
@app.route('/worker/<name>/alive')
def alive(name):
    # Caso o worker não esteja registado no servidor
    if not db.sismember(workersName, name): 
        return 'Worker not registered!'
    
    # Caso contrário, ir-se-á dar update à hora associada ao worker, visto que existiu comunicação.
    else: 
        data = db.get(name)
        data = json.loads(data)
        data["heartbit"] = str(datetime.datetime.now())
        db.set(name, json.dumps(data))
    return 'Heartbit OK'
     
# Endpoint a partir do qual os clientes podem dar upload de frames
@app.route('/', methods=['POST'])
def upload_file():
    if 'video' not in request.files:
        return "Incorrect parameters!", 400

    file = request.files['video']
    
    if file.filename == '':
        return 'Invalid file!', 400
    
    if file and allowed_file(file.filename):
        tic = time.perf_counter()
        tmp = tempfile.NamedTemporaryFile()
        file.save(tmp)
        thread = threading.Thread(target=processVideo, args=(tmp,), daemon=True)
        thread.start()
        return f"{file.filename} received!"

    return 'Invalid file!', 400

@app.errorhandler(404)
def page_not_found(e):
    return 'Error... Endpoint not found!', 404

def processVideo(video):
    vidcap = cv2.VideoCapture(video.name)
    success,image = vidcap.read()
    count = 0
    md5 = hashlib.md5(open(video.name, "rb").read()).hexdigest() #Criação do md5 identificador do vídeo 

    if not db.exists(str(md5+"_info")): # Receção de um vídeo novo
        db.set(str(md5+"_info"), "Splitting")
        while success:
            with tempfile.NamedTemporaryFile(prefix=md5+"_", suffix="_"+str((count+1))) as temp: #Ficheiro temporário com prefixo do identificador do vídeo
                    file = "".join([str(temp.name), ".jpg"])
                    cv2.imwrite(file,image)
                    success,image = vidcap.read()
                    
                    if(success):
                        data = {'file':file, 'md5': md5}
                        db.lpush(md5, json.dumps(data))
                    else:
                        data = {"nframes": count, "pframes": 0, "totaltime": 0, "avgTime": 0, "persons": 0, "classes": 0, "objects": {}}
                        data = json.dumps(data)
                        db.set(str(md5+"_info"), data)
                        db.lpush(videos, md5)

                    count += 1
    else: 
        data = db.get(str(md5+"_info"))
        if data != b'Splitting':
            data = json.loads(data)
            if int(data.get("pframes")) == int(data.get("nframes")): # Quer dizer que já foi processado e portanto volta-se a imprimir os resultados
                print("\nProcessed frames: "+str(data.get("pframes")))
                print("Average processing time per frame: "+str("{0:.3f}").format(data.get("avgTime"))+"ms")
                print("Person objects detected: "+str(data.get("persons")))
                print("Total classes detected: " +str(data.get("classes")))
                common = data.get("common")
                print("Top 3 objects detected: " + str(common[0][0]) + ", " +  str(common[1][0]) + ", " + str(common[2][0]))
                
# Função periódica que inicia uma thread separada a cada 30 segundos para verificar, um por um, se os workers
# que se encontram registados ainda estão ativos. 
def checkWorkers():
    for member in db.smembers(workersName):
        data = db.get(member)
        data = json.loads(data)

        if data: 
            tmp_date = datetime.datetime.strptime(data['heartbit'], '%Y-%m-%d %H:%M:%S.%f')
            time_now = datetime.datetime.now()
            
            if (time_now - tmp_date).total_seconds() > WAIT_SECONDS:
                # Assumir que morreu. Voltar a adicionar a frame à lista de frames por processar, mas adicionando-a pela direita,
                # uma vez que era suposto já ter sido processada e tem, portanto, mais prioridade.

                frame = data.get("frame")
                if frame:
                    dataFrame = json.loads(frame)
                    md5 = dataFrame.get("md5")

                    if db.llen(md5) == 0:
                        db.lpush(videos, md5)
                    dataPush = json.dumps(dataFrame)
                    db.rpush(md5, dataPush)
                    
                # Remover o worker
                db.delete(member)
                db.srem(workersName, member)
                print('\x1b[0;31;7m' + "Worker " + str(member.decode("utf-8")) + " removed."  + '\x1b[0m')

    thrd = threading.Timer(WAIT_SECONDS, checkWorkers)
    thrd.daemon = True
    thrd.start()
    return 

def acceptResults():
    while True:
        data = db.rpop("results")
        if data:
            data = json.loads(data)
            
            name = data.get("name")
            totalTime = data.get("time")
            printFrame = data.get("frame")
              
            md5 = data.get("md5")
            dataMd5 = db.get(str(md5+"_info"))
            dataMd5 = json.loads(dataMd5)

            objects = json.loads(data.get("objects"))
            personNumber = objects.get("person")

            # Não estando a ser detetadas pessoas no vídeo
            if not personNumber:
                personNumber = 0

            frame = dataMd5.get("pframes") + 1
            # Caso seja detetado um número de pessoas que exceda o valor limite definido.
            if (personNumber > int(args.max)):
                print('Frame ' + str(printFrame) + ': ' + str(personNumber) + ' <person> detected')

            # Update da informação com base no que o worker acaba de processar
            totalTime+= dataMd5.get("totaltime")
            dataMd5["totaltime"]= totalTime
            dataMd5["pframes"] = frame
            objects = Counter(Counter(dataMd5.get("objects"))+Counter(objects))
            dataMd5["objects"] = objects

            # Estatística impressa no fim do processamento de um vídeo
            if frame == int(dataMd5.get("nframes")):
                avgTime = totalTime/frame
                dataMd5["avgTime"] = avgTime
                persons = objects.get("person")
                dataMd5["persons"] = persons
                dataMd5["classes"] = len(objects)
                common = objects.most_common(3)
                dataMd5["common"] = common
                print("\nProcessed frames: "+str(frame))
                print("Average processing time per frame: "+str("{0:.3f}").format(avgTime)+"ms")
                print("Person objects detected: "+str(persons))
                print("Total classes detected: " +str(len(objects)))
                print("Top 3 objects detected: " + str(common[0][0]) + ", " +  str(common[1][0]) + ", " + str(common[2][0]))
                
            db.set(str(md5+"_info"), json.dumps(dataMd5)) 
        else:
            time.sleep(2)

    

def main(max_persons):
    checkWorkers()
    thread_RESULTS = threading.Thread(target=acceptResults, daemon=True)
    thread_RESULTS.start()
    app.run()
     

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--max', help='maximum number of persons in a frame', default=10)
    args = parser.parse_args()
    main(args.max)
