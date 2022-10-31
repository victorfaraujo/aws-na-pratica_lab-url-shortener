import json
import boto3 #AWS SDK para Python3
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
import decimal
from urllib.parse import urlparse
import time

# substitua essa variavel com o nome da tabela criada no DynamoDB
DYNAMODB_TABLE = "lab-urlshortener"
# subistitua essa variavel com a região da AWS onde sua tabela do DynamoDB foi criada
AWS_REGION = "us-west-2"

def roundFloat(o):
    """ Define o formato padrao para um decimal """
    if isinstance(o, decimal.Decimal):
        return int(o)
    raise TypeError

def getDynamoData(table: str, primaryKey: str, key: str, sortKey: dict = None):
    """Busca dados em uma tabela do DynamoDB
    Parametros:
        table: str [Obrigatório] Tabela a ser consultada
        primaryKey: str [Obrigatório] Chave da tabela que será consultada
        key: str [Obrigatório] Valor da chave que será consultado
        sortKey: dict [Opcional] Sort key da consulta no formato { "key": "xpto", "value": "xyz" }
        region: str [Opcional] Região da AWS onde a tabela foi criada. Default us-east-1
    """
    try:
        dynamo = boto3.client('dynamodb', region_name=AWS_REGION)
        s = TypeSerializer()
        key = { primaryKey: key }
        if sortKey:
            key[sortKey['key']] = sortKey['value']
        r = dynamo.get_item(
            TableName=table,
            Key={ k: s.serialize(v) for k, v in key.items() if v != "" }
        )
        d = TypeDeserializer()
        if "Item" in r:
            # chave localizada, retorna os dados
            return { "success": True, "message": "Ok", "data": json.loads(json.dumps({k: d.deserialize(value=v) for k, v in r['Item'].items()}, default=roundFloat)) }
        else:
            # chave não localizada, mas consulta realizada com sucesso
            return { "success": True, "message": "Nenhum dado localizado...", "data": None }
    except Exception as err:
        print("Falha ao obter dados do DynamoDB")
        print("Table: ", table)
        print("PrimaryKey: ", primaryKey)
        print("Key: ", key)
        print("Region: ", AWS_REGION)
        print(err)
        return { "success": False, "message": str(err), "data": {} }

def generateS3PreSignedURL(s3URI: str, ttl: int):
    """Gera uma URL pré-assinada de um arquivo do S3

    Parametros:
        s3URI: str - URI do Objeto S3
        ttl: integer - TTL do objeto para gerar uma URL que seja válida somente até o tempo definido
    """
    # transforma a URI do S3 em bcucket / object key
    bucket = s3URI.replace('s3://', '').split('/')[0]
    objectKey = s3URI.replace(f"s3://{bucket}/", '')
    # define o tempo de expiracao
    expiration = int(ttl) - int(time.time())
    try:
        client = boto3.client('s3')
        url = client.generate_presigned_url(
            ClientMethod='get_object',
            Params={
                'Bucket': bucket,
                'Key': objectKey
            },
            ExpiresIn=expiration
        )
        return { "success": True, "message": "Ok", "data": url }
    except Exception as err:
        print("Erro ao gerar URL pre-assinada:")
        print(err)
        return { "success": False, "message": str(err), "data": {} }

def redirectURL(code: str):
    """Função que procura o código informado na tabela do DynamoDB e redireciona a chamada
    
    Parâmetros:
        code: str - código informado via URI
    """
    try:
        if code != None and len(code) > 0:
            # codigo informado, busca dados na tabela do dynamoDB
            r = getDynamoData(DYNAMODB_TABLE, 'id', code)
            if not r['success']:
                # algum erro ao processar a requisicao no dynamoDB
                raise Exception(f"500|ERRO 500: {r['message']}")
            elif r['data']:
                # codigo localizado, verifica o tipo de protocolo se eh http ou s3
                if r['data']['urlOriginal'][:5].lower() == "s3://":
                    # uri do S3, gera uma URL auto assinada para redirecionar
                    s3url = generateS3PreSignedURL(r['data']['urlOriginal'], r['data']['dataExclusao'])
                    if s3url['success']:
                        # url pre assinada gerada com sucesso, retorna os dados
                        redirect = s3url['data']
                    else:
                        # algum erro ao tentar gerar a url pre assinada do S3, retorna erro 500
                        raise Exception(f"500|ERRO 500: {s3url['message']}")
                else:
                    # url normal, envia para redirecionamento
                    redirect = r['data']['urlOriginal']
                # retorna o redirecionamento
                return {
                    "status": 302, # http code para redirecionamento temporário
                    "headers": {
                        "content-type": [{"key": "Content-Type", "value": "text/html; charset=utf-8"}],
                        "access-control-allow-origin": [{"key": "Access-Control-Allow-Origin", "value": "*"}],
                        "allow": [{"key": "Allow", "value": "GET, OPTIONS"}],
                        "location": [{"key": "Location", "value": redirect}],
                        "host": [{"key": "Host", "value": urlparse(redirect).netloc}],
                        "access-control-allow-methods": [{"key": "Access-Control-Allow-Methods", "value": "GET, OPTIONS"}],
                        "access-control-allow-headers": [{"key": "Access-Control-Allow-Headers", "value": "*"}]
                    },
                    "body": "Redirecionando..."
                }
            else:
                # código nao localizado, retorna erro 404
                raise Exception("404|ERRO 404: O endereço informado não foi localizado.")
        else:
            # código não informado, retorna erro 400
            raise Exception("400|ERRO 400: Dados necessários não informados.")
    except Exception as err:
        error = str(err).split("|")
        return {
            "status": int(error[0]),
            "headers": {
                "content-type": [{"key": "Content-Type", "value": "text/html; charset=utf-8"}],
                "access-control-allow-origin": [{"key": "Access-Control-Allow-Origin", "value": "*"}],
                "allow": [{"key": "Allow", "value": "GET, OPTIONS"}],
                "access-control-allow-methods": [{"key": "Access-Control-Allow-Methods", "value": "GET, OPTIONS"}],
                "access-control-allow-headers": [{"key": "Access-Control-Allow-Headers", "value": "*"}]
            },
            "body": str(error[1])
        }

def lambda_handler(event, context):
    """Função principal da aplicação, essa função deve ser informada como a "handler" do Lambda

    Parâmetros: 
        event: dict - Contém os dados do evento que foi o acionador do Lambda
        context: dict - Contém os dados do contexto da requisição, dados do ambiente, id da requisição, etc...
    """
    # funcao principal da aplicação, responsável por receber os dados do evento e contexto da requisição
    print("Dados do evento recebido:")
    print(event)
    print("Dados do contexto recebido:")
    print(context)
    # O evento repassado pelo CloudFront, envia os dados em forma de lista dentro de 'Records', para facilitar irei adicionar o primeiro item da lista a variável record
    record = event['Records'][0]
    # a uri é informada dentro da estrutura do dicionário do record, no caminho cf > request -> uri,vamos verificar se esse caminho foi informado.
    if "cf" in record and record['cf'] and "request" in record['cf'] and record['cf']['request'] and "uri" in record['cf']['request'] and record['cf']['request']['uri']:
        # obtem o código informado via uri e remove a "/" inicial
        code = record['cf']['request']['uri'][1:]
        # retorna os dados do redirecionamento
        return redirectURL(code)
    else:
        # uri não informada logo nao é possível fazer o redirect, retorna erro 400 para indicar que o usuário não informou os dados de entrada corretamente.
        return {
            "status": 400,
            "headers": {
                "content-type": [{"key": "Content-Type", "value": "text/html; charset=utf-8"}],
                "access-control-allow-origin": [{"key": "Access-Control-Allow-Origin", "value": "*"}],
                "allow": [{"key": "Allow", "value": "GET, OPTIONS"}],
                "access-control-allow-methods": [{"key": "Access-Control-Allow-Methods", "value": "GET, OPTIONS"}],
                "access-control-allow-headers": [{"key": "Access-Control-Allow-Headers", "value": "*"}]
            },
            "body": "ERRO 400: Dados necessários não informados."
        }