


# Computação Distribuída - Trabalho 2

## Sistema Distribuído de Deteção de Objetos

Este trabalho visa a criação de um sistema distribuído de deteção de objetos, sendo necessário estabelecer comunicação entre workers e o servidor, concebido com base na framework Flask, e entre este e os clientes.

O fluxo resume-se no cliente enviar um vídeo para que o servidor possa dividir o mesmo em frames. O servidor comunica maioritariamente com uma instância do Redis, verificando, introduzindo ou obtendo dados da base de dados para todas as funções que realiza. Paralelamente, os workers estão constantemente a tentar obter frames para processar.

##  Preparação
Estas instruções ajudarão a executar os programas desenvolvidos:

  ```
  $ brew install redis | sudo apt install redis-server
  $ python3 -m venv venv
  $ source venv/bin/activate
  $ python -m pip install --upgrade pip
  $ pip install -r requirements.txt
  $ wget https://pjreddie.com/media/files/yolov3.weights
  ```


## Detalhes

É possível encontrar todos os detalhes no [Relatório do Trabalho](./relatorio/Distributed_Object_Detection.pdf).

## Autores

 - **[Hugo Paiva de Almeida](https://github.com/hugofpaiva) - 93195** 
 - **[Carolina Araújo](https://github.com/carolinaaraujo00) - 93248**

 ## Nota
Classificação obtida de **19.5** valores em 20.
