#!/usr/bin/env python3
# coding=utf-8
import sys
from oracle import do_oracle
import json
import requests
import logging
import yaml

from rich.logging import RichHandler
from utils.log import LogFilter
from utils.conf import load_config
from utils.meta import print_meta
from pathlib import Path

import sys
import os

# Ajouter le chemin du projet à PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()],
    )

logger = logging.getLogger("LLM Triage")

# Chargement de la configuration
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
config_file_path = THIS_DIR + '/config.yaml'  # Remplace par le chemin vers ton fichier YAML
config = load_config(config_file_path)


# Données à envoyer
data = {
    "api_key": config.get('api_key'),
    "count": config.get("count"),
    "type": "Telegram"
}


# Functions
def getparam(count):
    """Retrieve the parameters appended """
    if len(sys.argv) != count + 1:
        logger.info('My command')
        logger.info('To Use: %s my params' % sys.argv[0])
        sys.exit(1)
    else:
        return sys.argv[1]


def post_data(tags, markdown, uri):

    data = {
        "api_key": config.get("api_key"),
        "uri": uri,
        "type": "Telegram",
        "ai_tags_add": tags,  # En utilisant la variable array tags
        "ai_classified": True,  # ai_classified à True
        "ai_summary": markdown  # avec la variable markdown
        }

    # Effectuer la requête POST
    response = requests.post(config.get("urlupd"), headers={"Content-Type": "application/json"}, data=json.dumps(data))

    # Afficher la réponse
    if response.status_code == 200:
        logger.info(response.json())  # Si la réponse est en JSON
    else:
        logger.info(f"Erreur {response.status_code} : {response.text}")

def ask_oracle(jobs):
    for line in jobs:
        logger.info(f"do_oracle {line[0]}")
        try:
            tags, markdown = do_oracle(line[0])
            post_data(tags, markdown, line[1])
        except ValueError:
            logger.warning(f"L'oracle a merdé... try again")
            try:    
                tags, markdown = do_oracle(line[0])
                post_data(tags, markdown, line[1])
            except ValueError: 
                logger.warning(f"L'oracle a merdé... see you next time")
        except openai.error.APIError as e:
            logger.warning(f"API Error {e}")



# Main Code #####
def main():
    # curl -X POST -H "Content-Type: application/json" -d '{"api_key": "zoubida", "count": 5, "type": "telegram"}' http://127.0.0.1:5000/api/get_ai_job

    # Effectuer la requête POST
    response = requests.post(config.get("url"), headers={"Content-Type": "application/json"}, data=json.dumps(data))

    if response.status_code == 200:
        logger.info("query ok")
        json_data =response.json()  # Si la réponse est en JSON
        logger.info(json_data)
        if json_data.get('data') == True:
            ask_oracle(json_data.get('objects'))
    else:
        logger.info(f"Erreur {response.status_code} : {response.text}")

if __name__ == '__main__':
    main()
