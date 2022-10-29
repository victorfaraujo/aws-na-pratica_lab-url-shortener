import json
from uuid import uuid4
import boto3 #AWS SDK para Python3
from boto3.dynamodb.types import TypeSerializer, TypeDeserializer
from datetime import datetime, timezone, timedelta
import decimal
import random
import string

# substitua essa variavel com o nome da tabela criada no DynamoDB
DYNAMODB_TABLE = "lab-urlshortener"
# subistitua essa variavel com a região da AWS onde sua tabela do DynamoDB foi criada
AWS_REGION = "us-west-2"
# substitua essa variavel com o DOMINIO que você utilizará
APP_DOMAIN = "lab-academy.cf"

def roundFloat(o):
    """ Define o formato padrao para um decimal """
    if isinstance(o, decimal.Decimal):
        return int(o)
    raise TypeError

def putItemDynamoDB(table, item):
    """Função que adiciona um novo item a uma tabela do DynamoDB

    Parâmetros:
        table: str [Obrigatório] Tabela onde o item será armazenado
        item: dict [Obrigatório] Item no formato JSON
    """
    try:
        dynamo = boto3.client('dynamodb', region_name=AWS_REGION)
        s = TypeSerializer()
        r = dynamo.put_item(
            TableName=table,
            Item={k: s.serialize(v) for k, v in item.items() if v != ""}
        )
        print("Resultado do PUT ITEM:")
        print(r)
        return { "success": True, "message": "Dados gravados com sucesso.", "data": { "id": item['id'] } }
    except Exception as err:
        print("Falha ao gravar no DynamoDB")
        print("Tabela: ", table)
        print("Item: ", item)
        print("Regiao: ", AWS_REGION)
        print(err)
        return { "success": False, "message": err, "data": {} }

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

def sec2Epoch(seconds: int):
    """Função que transforma segundos em EPOCH
    
    Parâmetros:
        seconds: int - Numero de segundos a ser convertido
    """
    seconds = seconds if seconds else (60 * 60 * 24 * 365 * 100) # se os segundos não foram informados, considera um prazo de 100 anos pra remover da tabela :)
    expireIn = datetime.now(tz=timezone.utc) + timedelta(seconds = seconds)
    return int(round(expireIn.timestamp()))

def generateCode(alias: str):
    """Função que gera um código aleatório para ser utilizado como código do encurtador, se tiver sido informado um alias, verifica se é válido e retorna os dados

    Parâmetros:
        alias: str - codigo sugerido pelo cliente para utilizar como alias do encurtador
    """
    if alias:
        # cliente informou um alias, verifica se ele já está em uso
        r = getDynamoData(DYNAMODB_TABLE, 'id', alias)
        if not r['success']:
            # falha ao acessar o dynamodb, retorna erro
            return { "success": False, "message": r['message'] }
        elif not r['data']:
            # consulta ok e não existe o codigo, retorna o codigo
            return { "success": True, "data": alias }
        else:
            # consulta ok mas já existe o codigo gravado, retorna erro
            return { "success": True, "data": None }
    else:
        # alias não informado, gera um código aleatório
        invalid = True
        while invalid:
            code = ''.join(random.sample(string.ascii_lowercase + string.digits, 8))
            r = getDynamoData(DYNAMODB_TABLE, 'id', code)
            if not r['success']:
                # falha ao acessar o dynamodb, retorna erro
                invalid = False # apenas para garantir que o loop será encerrado
                return { "success": False, "message": r['message'] }
            elif not r['data']:
                # consulta ok e não existe o codigo, codigo gerado ok, encerra o loop
                invalid = False
        return { "success": True, "data": code }

def generateShortenerURL(data: dict):
    """Função que irá gerar a URL encurtada e salvará os dados no DynamoDB

    Parâmetros:
        data: dict - dicionários com os dados necessários para criação da url encurtada
    """
    # gera o código da URL
    code = generateCode(data['id'])
    if code['success']:
        # verifica se foi gerado um codigo
        if not code['data']:
            # o alias informado já está gravado na tabela e nao pode ser utilizado
            return { 
                "success": False, 
                "message": "Alias informado já está sendo utilizado para outro endereço."
            }
        # adiciona o codigo como identificador
        data['id'] = code['data']
        # cria a URL encurtada
        data['urlEncurtada'] = f"https://{APP_DOMAIN}/{code['data']}"
        # grava os dados no DynamoDB
        r = putItemDynamoDB(DYNAMODB_TABLE, data)
        # testa o retorno
        if r['success']:
            # tudo certo, devolve a URL criada
            return {
                "success": True,
                "message": "Ok",
                "data": {
                    "code": data['id'],
                    "urlEncurtada": data['urlEncurtada'],
                    "urlOriginal": data['urlOriginal'],
                    "validade": f"{datetime.fromtimestamp(int(data['dataExclusao'])).strftime('%Y-%m-%dT%H:%M:%S%z')[:-2]}:00"
                }
            }
        else:
            # falha ao gravar, retorna o erro
            return {
                "success": False,
                "message": f"Falha ao gravar na tabela {r['message']}"
            }
    else:
        # falha ao gerar o codigo retorna o erro
        return {
            "success": False,
            "message": f"Falha ao gerar o código: {code['message']}"
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
    # como nosso único campo obrigatório é o url verifica se foi informado
    if "url" in event and event['url'] != None:
        # verifica os campos obrigatorios foram informados e adiciona a um dicionario que será gravado no DynamoDB
        data = {
            "id": event['alias'] if "alias" in event and event['alias'] else None,
            "urlOriginal": event['url'],
            "urlEncurtada": None,
            "dataExclusao": sec2Epoch(int(event['ttl'])) if "ttl" in event and event['ttl'] else sec2Epoch(None), # transforma os segundos enviados em epoch, ou considera para remover daqui 100 anos :)
            "ttl": event['ttl'] if "ttl" in event and event['ttl'] else None
        }
        # dados iniciais 
        return generateShortenerURL(data)
    else:
        # se o nome não foi informado retorna uma mensagem de erro
        return {
            "success": False,
            "message": "Campo URL não foi informado."
        }