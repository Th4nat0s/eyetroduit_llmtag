import json 
import openai
import sys
from clickhouse_driver import Client
# import clickhouse_connect
import tiktoken
import logging
from rich.logging import RichHandler
from utils.log import LogFilter
from utils.conf import load_config
from utils.meta import print_meta
from pathlib import Path
import os
import re
import inflect

# Ajouter le chemin du projet à PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

plu = inflect.engine()

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
config_file_path = THIS_DIR + '/config.yaml'  # Remplace par le chemin vers ton fichier YAML
config = load_config(config_file_path)

if config.get('log_level').upper() == "DEBUG":
    log_level =     logging.DEBUG
else:
    log_level =     logging.INFO

logging.basicConfig(
    level=log_level,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler()],
    )
logger = logging.getLogger("media_downloader")


openai.api_key = config.get('ai_key')

BAD_LBL = ["likes", "active", "cyber", "Awarene"]

# Reclassification manuelle des label
REP_LBL = {"advertisement": ["spam", "pub", "ads", "ad", "advertisementvertisement", "promotions", "marketing", "advertising"],
           "ddos": ["tcp", "flood"], 
           "testimonial": ["vouch"],
           "credsdumps": ["combos", "datatheft", "credentials", "theft", "accounts", "informati", "Acce", "creds_dumps" ],
           "trolling": ["cha"],
           "hosting": ["kyc"],
           "proxies": ["proxie", "proxiess"],
           "anonymous": ["anonymou"],
           "cyberattack" : ["cyberwar", "defacement", "breaches", "cyberwarfare", "cybercrime"],
           "hacktivism": ["cyberunity", "cyberjihad", "opterrorism", "ilent_cyber_force", "hacktivist"],
           "opindia": ["op_india"],
           "databreach": ["data_breach"],
           "propaganda": ["opinis"]
          }


# La question pour la qualification initiale
context_query = '''
        This is an excerp of a telegram channel messages. Classify the channel using labels.
        Give 10 labels.
        The label MUST be short, with one word maximum in english.
        label what is the most frequent.
        When possible, Use this syntax of label, but don't hesitate to gives more custom and acurate labels.

        law_enforcement: Related to channels of police/gvt and LE actions against threat actors.
        Carding: Related to selling, fraud, or illegal activities involving credit cards.
        hacking_claim: revendication of threat actors about website compromises or pride in breaching systems.
        CredsDumps: Related to credential leaks for download or share.
        Leaks: Pertaining to company leaks after hacks, such as SQL database dumps.
        DDoS: Discussing DDoS activities, claims of attacks, or selling DDoS tools.
        Ponzi/Financial: Related to financial gain or investment schemes.
        Testimonial: Evidence of payments or proof that a service is legitimate. it does not includes greetings to groups.
        Hosting: if it talk about AWS, Azure, and Digital Ocean accounts, often at discounted prices.
        
        You may add more label of your choice if you find it relevant.

        IMPORTANT: Select labels to permit discrimination between channels containing valuable information or mostly hacking service advertisements.
        It is also IMPORTANT to label if the channel deliver really leaks and credential dumping samples.
        IMPORTANT: Give the labels as a csv, don't forget the comma.
        '''

# Question de validation
justif_query = '''
        Following is messages collected on a telegram channel.
        Gives a small resume of the channel.
        Then since you have classified this telegram channel with some keywords, for each keyword
        give an explanation of what you have see in the text.

        Take the following in consideration
        label credsdumps should be true only if credentials are directly available in the chat, of if file name suggests a dataleak file.
        label hacking_claim should be true only if a hacking against a identified victim is available and revendicated by the attacker.
        label carding should be true only if there is cc exchange or any comments on how to steal CC.
        label law_enforcement to true, only if it's an channel maintained by law enforcement talking about their actions.

        WARNING: The output should be in RAW JSON that should follow this format
        {
          "channel_summary": {
          "description": "The Telegram channel description…"
           },
          "keyword_classifications": {
          "label1": {
            "justification": "Explanation why this classification...",
            "match": True or False ...if the keyword apply to theses messagyyyes
                    },
          "label2": {
            "justification": "Explanation why this classification..."
            "match": True or False ...if the keyword apply to theses messagyyyes
                    } etc...,
       
        The keyword that you have to justify are;\n
        '''

def reclassify_labels(labels, mapping):
    # Parcours de chaque étiquette dans labels
    for i, lbl in enumerate(labels):
        # Parcours des clés et des listes associées dans le dictionnaire
        for key, values in mapping.items():
            # Si l'étiquette correspond à une valeur dans la liste, on la remplace par la clé
            if lbl in values:
                labels[i] = key
                break  # On sort de la boucle interne une fois la correspondance trouvée
    return labels

def pluriel(mot):
    # Liste d'acronymes ou de termes techniques à traiter comme exceptions
    acronymes = ["ddos", "credsdumps"]  # Mots invariables
    if mot.lower() in acronymes:
        return mot 
    return plu.plural(mot)


def json2markdown(data):
    # Récupérer la description du channel
    markdown = "### Channel Summary\n"
    markdown += f"{data['channel_summary']['description']}\n\n"

    # Ajouter les classifications de mots-clés avec match à True
    markdown += "### AI Keyword Classifications\n\n"
    for key, value in data["keyword_classifications"].items():
        if value["match"]:  # Si le match est True
            markdown += f"#### {key.capitalize()}\n"
            markdown += f"- **Justification**:  {value['justification']}\n\n"
    return(markdown)


# Fonction pour interroger l'API GPT-3.5 Turbo
def poser_question(context, query):
    real_query = query
    response = openai.ChatCompletion.create(
        #model="gpt-3.5-turbo",
        # model="gpt-4",
        model = "gpt-4o-mini",
        temperature=0.4,
        messages=[
            {"role": "system", "content": "You are a treat intelligence security analyst and you should classify by label telegram channels"},
            {"role": "user", "content": context +  real_query}
        ]
    )
    return response.choices[0].message['content'].strip()

def clean_underscores(arr):
    # Traise les __ devant a la fin...
    result = []
    for item in arr:
        cleaned_item = re.sub(r'^_+|_+$', '', item)  # Enlève les _ du début et de la fin
        cleaned_item = re.sub(r'_+', '_', cleaned_item)  # sed les __ en un \_
        if cleaned_item:  # Vire les ____ 
            result.append(cleaned_item)
    return result

def fix_ai(result, question):
    result = result.lower()     # Lowercase convesion
    result = result.strip('```json').strip('```').strip()  # cette merde comprends pas que je veux un putain de json juste
    result = result.replace("\n", ",")  # si des \n , on mets des ,  , defois cette bouse mets du texte au lieux des labels.
    result = result.split(',')  # String to array
    logger.info(f"Initials labels : {result}")

    result = [item.strip() for item in result] # remove spaces
    result = [re.sub(r'^\d+\. ', '', label) for label in result]  # vire les 1. xxx 2. XX qui lui prends défois.
    result = list(set(result)) # be sure of uniqueness
    result = [item for item in result if not " " in item] # vire les truc a space
    result = [re.sub(r'[^a-zA-Z0-9_]', '_', label.strip()) for label in result]  # on vire ce qui est pas ascii.
    result = clean_underscores(result)

    result = [item for item in result if item not in BAD_LBL] # Block some labels
    # Réducteur de créativité 
    result = reclassify_labels( result, REP_LBL)

    # Fix hallucination.
    if "ddos" in result:
        ddos_lbl = [ "ddos", "flood", "check-host" ]
        lquestion = question.lower()
        contains_ddos = False
        for word in ddos_lbl:
            if word in lquestion:
                contains_ddos = True
                logger.info("No hallucination on DDOS")
                break
        if not contains_ddos:
            logger.warning("Hallucination on DDOS")
            result.remove("ddos")

    #result = [ plu.singular_noun(item) for item in result]
    result = [ pluriel(item) for item in result]

    result = list(set(result)) # be sure of uniqueness
    return(sorted(result))


def fetch_messages(chan_id, count):
    # Connexion à la base de données ClickHouse
    # client = clickhouse_connect.get_client(host=CLICKHOUSE, port=9000) # 8123)  # 9000)
    client = Client(host=config.get("CLICKHOUSE"), port=9000) # 8123)  # 9000)

    
    # Exécution de la requête pour récupérer les messages
    query = f"""
        SELECT text, document_name, document_present 
        FROM {config.get("DATABASE")}.{config.get("TABLE")} 
        WHERE chat_id = {chan_id} AND (text != '' OR document_present = 1) 
        ORDER BY date DESC 
        LIMIT {count}
    """
    # result = client.query(query)
    logger.debug(f"SQL: {query}")
    result = client.execute(query)

    # Récupérer les messages (chaque ligne est un tuple contenant : le texte, le nom du document et la présence de document)
    messages = result # .result_rows

    if len(messages) == 0:
        return "but since No telegram message, return the label 'Empty' "

    # Construire la chaîne de texte avec "Someone wrote:\n" ou "file attached : {document_name}" si un document est présent
    formatted_result = ""
    document_count = 0
    for text, document_name, document_present in messages:
        if document_present:
            document_count += 1 
            formatted_result += f"Message:\n{text}\nfile attached: {document_name}\n"
        else:
            formatted_result += f"Messages:\n{text}\n"

    # logger.info(f"{document_count} docs for {len(messages)} messages")
    return (formatted_result, document_count, len(messages))


def estimate_tokens(text, model="gpt-3.5-turbo"):
    # Charger l'encodeur correspondant au modèle
    enc = tiktoken.encoding_for_model(model)
    
    # Convertir la chaîne en tokens
    tokens = enc.encode(text)
    
    # Retourner le nombre de tokens
    return len(tokens)


def main():
    # Vérifier si un argument a été fourni
    if len(sys.argv) != 2:
        logger.info("Usage: python script.py <chan_id>")
        sys.exit(1)

    # Récupérer le premier argument
    chan_id = sys.argv[1]
    do_oracle(chan_id)


def do_oracle(chan_id):

    # Afficher l'argument
    logger.info(f"Le chan_id est : {chan_id}")

    # Exemple d'appel de la fonction avec un chan_id donné
    i= 250
    question, documents, lenquestion = fetch_messages(chan_id, i)
    token_count = estimate_tokens(question)
    logger.info(f"Token for 250 msg: {token_count}")
    pmt = token_count / 250
    evaluate = 8192 / pmt
    logger.info(f"Need {int(evaluate)} for ~ {pmt*evaluate}Token")
    i = int(evaluate) + 10

    question, documents, lenquestion = fetch_messages(chan_id, i)
    token_count = estimate_tokens(question)
    logger.info(f"Token for {i} msg {token_count}")

    while token_count > 8192:
        token_count = estimate_tokens(question)
        i = i -  3
        question, documents, lenquestion = fetch_messages(chan_id, i)
        logger.info(f"Token Size {token_count}… Adjusting")

    if token_count < 150:
        logger.warning(f"Token Size to small {token_count}")
        logger.debug(f"Documents: \n {documents}")
        return(["ai_low_token"], "### Not enough data for LLM analysis")


    logger.info(f"Le nombre de tokens est : {token_count}")
    if documents>0:
        logger.info(f"{documents} docs for {lenquestion}, ratio {lenquestion/documents}")
    result = poser_question(context_query, question)
    result = fix_ai(result, question)
    logger.info(result)
    keywords = result

    # global context_query
    query = justif_query + str(result) + "\n and here are the messages:\n"
    result = poser_question(query, question)
    result = result.strip('```json').strip('```').strip()  # cette merde comprends pas que je veux un putain de json juste
    logger.info(f"{result}") 
    try:
        json_data = json.loads(result)
    except json.JSONDecodeError as e:
        raise ValueError("L'AI est trop conne pour pondre un JSON dans 100% des cas")


    # Filter keywords based on the match status
    filtered_keywords = [
        keyword for keyword in keywords
        if json_data["keyword_classifications"].get(keyword, {}).get("match", False)
            ]

    

    logger.info(result)
    logger.info(filtered_keywords)
    logger.info(80*"-")
    logger.info(json2markdown(json_data))

    return(filtered_keywords, json2markdown(json_data))

if __name__ == "__main__":
    main()




