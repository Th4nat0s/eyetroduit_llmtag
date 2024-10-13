import yaml

def load_config(file_path):
    """
    Charge un fichier YAML et retourne son contenu sous forme de dictionnaire.
    """
    with open(file_path, 'r') as file:
        config = yaml.safe_load(file)
    return config

