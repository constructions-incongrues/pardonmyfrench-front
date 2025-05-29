#!/usr/bin/env python
import os
import re
import yaml
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin, urlparse
import unicodedata
import argparse
import shutil

def slugify(text):
    """Convertit un texte en slug."""
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    text = re.sub(r'[^\w\s-]', '', text.lower())
    text = re.sub(r'[-\s]+', '-', text).strip('-_')
    return text

def download_file(url, output_path, max_retries=3):
    """Télécharge un fichier depuis une URL avec gestion des erreurs et des tentatives."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, stream=True, timeout=10)
            response.raise_for_status()
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, 'wb') as file:
                shutil.copyfileobj(response.raw, file)
            return output_path
        except Exception as e:
            print(f"Erreur lors du téléchargement (tentative {attempt+1}/{max_retries}): {e}")
            if os.path.exists(output_path):
                os.remove(output_path)
            if attempt == max_retries - 1:
                raise
            time.sleep(2)  # Petite pause avant de réessayer

def get_songs(base_url):
    """Récupère les chansons du site."""
    response = requests.get(base_url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    songs = []

    # Trouver les liens vers les pages de chansons
    for el in soup.find_all('li', class_='song'):
        # ID de la chanson
        song_id = el['id'].replace('song', '')

        # Titre, artistes
        cover = el.find('span', class_='cover').text.strip().split(' - ')

        # Artiste et titre original
        original = el.find('span', class_='original').text.strip().replace('\n', '').replace('\t', '').split(' - ')
        if len(original) < 2:
            continue

        # Paroles
        actions = el.find('div', class_='actions')
        actions_links = actions.find_all('a', class_='mp3')

        songs.append({
            'id': song_id,
            'contributors': cover[0].strip(),
            'title': cover.pop().strip(),
            'lyrics_url': base_url + "/" + requests.utils.unquote(actions_links[2]['href'].strip()) if len(actions_links) > 2 else "",
            'original_title': original.pop().strip(),
            'original_artist': original[0].strip(),
            'original_clip_url': requests.utils.unquote(actions_links[1]['href'].strip()) if len(actions_links) > 1 else "",
            'audio_url': base_url + "/" + requests.utils.unquote(actions_links[0]['href'].strip()) if len(actions_links) > 0 else "",
        })

    return songs

def save_song_data(song_data, output_dir, force_download=False):
    """Sauvegarde les données d'une chanson dans le format requis."""
    if not song_data:
        return None

    # Créer un slug pour le dossier de la chanson
    slug = slugify(f"{song_data['contributors']}-{song_data['title']}")
    song_dir = os.path.join(output_dir, slug)

    # Créer le dossier si nécessaire
    os.makedirs(song_dir, exist_ok=True)

    # Préparer les données pour le frontmatter
    frontmatter_data = {
        'id': int(song_data['id']),
        'is_published': True,
        'title': song_data['title'],
        'contributors': song_data['contributors'],
        'original_title': song_data['original_title'],
        'original_artist': song_data['original_artist'],
        'original_clip_url': song_data['original_clip_url']
    }

    # Récupérer le contenu du fichier de paroles
    print(f"[song/{song_data['id']}] Téléchargement des paroles")
    try:
        with requests.get(song_data['lyrics_url']) as response:
            response.raise_for_status()
            lyrics = response.text
            frontmatter_data['lyrics'] = lyrics
    except Exception as e:
        print(f"[song/{song_data['id']}] Erreur lors du téléchargement des paroles : {e}")
        frontmatter_data['lyrics'] = ""

    # Gérer l'audio si disponible
    if song_data['audio_url']:
        try:
            audio_filename = os.path.basename(urlparse(song_data['audio_url']).path)
            audio_path = os.path.join('chansons', slug, audio_filename)
            local_audio_path = os.path.join(output_dir, '..', audio_path)

            # Récupérer la date Last-Modified de l'audio
            try:
                head_resp = requests.head(song_data['audio_url'], allow_redirects=True)
                last_modified = head_resp.headers.get('Last-Modified')
                if last_modified:
                    # Convertir la date en format ISO
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(last_modified)
                    frontmatter_data['date'] = dt.date().isoformat()
                else:
                    frontmatter_data['date'] = ""
            except Exception as e:
                print(f"[song/{song_data['id']}] Impossible de récupérer la date Last-Modified : {e}")
                frontmatter_data['date'] = ""

            # Vérifier si le fichier existe déjà
            if not os.path.exists(local_audio_path) or force_download:
                print(f"[song/{song_data['id']}] Téléchargement de l'audio")
                download_file(song_data['audio_url'], local_audio_path)
            else:
                print(f"[song/{song_data['id']}] Audio déjà téléchargé pour, saut du téléchargement.")

            # Ajouter le chemin de l'audio au frontmatter
            frontmatter_data['audio'] = f"/{audio_path}"
        except Exception as e:
            print(f"[song/{song_data['id']}] Erreur lors du téléchargement de l'audio : {e}")
            frontmatter_data['audio'] = ""
            frontmatter_data['date'] = ""
    else:
        frontmatter_data['audio'] = ""
        frontmatter_data['date'] = ""

    # Créer le contenu du fichier
    content = "---\n"
    content += yaml.dump(frontmatter_data, allow_unicode=True)
    content += "---\n"

    # Sauvegarder le fichier
    file_path = os.path.join(song_dir, 'chanson.md')
    with open(file_path, 'w', encoding='utf-8') as file:
        file.write(content)

    return file_path

def main():
    parser = argparse.ArgumentParser(description='Scraper pour pardon-my-french.fr')
    parser.add_argument('--output', default='site/chansons', help='Dossier de sortie pour les chansons')
    parser.add_argument('--force-download', action='store_true', help='Forcer le téléchargement des fichiers audio')
    args = parser.parse_args()

    base_url = "https://pardon-my-french.fr"
    output_dir = args.output
    force_download = args.force_download

    print(f"[songs] Récupération des chansons depuis {base_url}")
    songs = get_songs(base_url)
    print(f"[songs] Trouvé {len(songs)} chansons.")

    for song in songs:
        print(f"[song/{song['id']}] Récupération de la chanson")
        save_song_data(song, output_dir, force_download)

    print(f"[songs] Chansons sauvegardées dans {output_dir}.")

    print("[songs] Terminé!")

if __name__ == "__main__":
    main()