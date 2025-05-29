import os
import subprocess
import re
import sys
import yaml
import logging

# Configuration du logger
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

def update_chanson_md(mp3_path, oid):
    chanson_dir = os.path.dirname(mp3_path)
    md_path = os.path.join(chanson_dir, "chanson.md")
    if not os.path.exists(md_path):
        logger.warning(f"Aucun fichier chanson.md trouvé pour {mp3_path}")
        return

    logger.info(f"Mise à jour du frontmatter de {md_path} avec l'OID {oid}")
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Impossible de lire {md_path} : {e}")
        return

    # Séparation du frontmatter YAML et du contenu
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            body = parts[2]
        else:
            logger.error(f"Frontmatter YAML mal formé dans {md_path}")
            return
    else:
        logger.error(f"Pas de frontmatter YAML dans {md_path}")
        return

    try:
        data = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as e:
        logger.error(f"Erreur de parsing YAML dans {md_path} : {e}")
        return

    data["mp3_oid"] = oid

    try:
        new_frontmatter = yaml.dump(data, allow_unicode=True, sort_keys=False)
        new_content = f"---\n{new_frontmatter}---{body}"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        logger.info(f"Frontmatter mis à jour dans {md_path}")
    except Exception as e:
        logger.error(f"Impossible d'écrire dans {md_path} : {e}")

def get_mp3_oids(chansons_dir):
    mp3_oids = {}
    logger.info(f"Recherche des fichiers .mp3 dans : {chansons_dir}")
    for root, _, files in os.walk(chansons_dir):
        for file in files:
            if file.endswith('.mp3'):
                mp3_path = os.path.join(root, file)
                logger.debug(f"Fichier trouvé : {mp3_path}")
                try:
                    logger.info(f"Exécution de la commande : git lfs ls-files --long --include={os.path.dirname(mp3_path)}")
                    output = subprocess.check_output(
                        ['git', 'lfs', 'ls-files', '--long', '--include=%s' % os.path.dirname(mp3_path)],
                        text=True
                    )
                    logger.debug(f"Sortie git lfs : {output.strip()}")
                    match = re.match(r'^([0-9a-f]{64})', output)
                    if match:
                        oid = match.group(1)
                        mp3_oids[mp3_path] = oid
                        logger.info(f"OID trouvé pour {mp3_path} : {oid}")
                        update_chanson_md(mp3_path, oid)
                    else:
                        logger.warning(f"Aucun OID trouvé pour {mp3_path}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Erreur lors de l'exécution de git lfs pour {mp3_path} : {e}")
                    mp3_oids[mp3_path] = None
                except Exception as e:
                    logger.error(f"Erreur inattendue pour {mp3_path} : {e}")
                    mp3_oids[mp3_path] = None
    return mp3_oids

if __name__ == "__main__":
    if len(sys.argv) != 2:
        logger.error(f"Usage: {sys.argv[0]} <chansons_dir>")
        sys.exit(1)
    chansons_dir = sys.argv[1]
    logger.info(f"Démarrage du script avec le dossier : {chansons_dir}")
    try:
        oids = get_mp3_oids(chansons_dir)
        for path, oid in oids.items():
            print(f"{path}: {oid}")
    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'exécution du script : {e}")
        sys.exit(2)