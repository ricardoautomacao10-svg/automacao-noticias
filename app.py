# ==============================================================================
# BLOCO 1: IMPORTAÇÕES
# ==============================================================================
import os
import io
import json
import requests
import textwrap
import subprocess
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from base64 import b64encode

# ==============================================================================
# BLOCO 2: CONFIGURAÇÃO INICIAL
# ==============================================================================
load_dotenv()
app = Flask(__name__)

# Configs do WordPress e Meta (mesmos de antes)
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}
META_API_TOKEN = os.getenv('META_API_TOKEN')
BOCA_INSTAGRAM_ID = os.getenv('BOCA_INSTAGRAM_ID')

# ==============================================================================
# BLOCO 3: FUNÇÕES AUXILIARES
# ==============================================================================
def criar_video_reels_com_ffmpeg(url_imagem, manchete, url_logo, url_musica):
    print(f"🎬 Começando a criação do vídeo com FFmpeg...")
    try:
        # Download dos assets para arquivos temporários
        with open("imagem_noticia.jpg", "wb") as f:
            f.write(requests.get(url_imagem).content)
        with open("logo.png", "wb") as f:
            f.write(requests.get(url_logo).content)
        with open("musica.mp3", "wb") as f:
            f.write(requests.get(url_musica).content)
        
        # Prepara o texto para o ffmpeg (escapando caracteres especiais)
        manchete_escapada = manchete.replace("'", "'\\''")

        # Comando FFmpeg
        comando = [
            'ffmpeg',
            '-loop', '1', '-i', 'imagem_noticia.jpg', # Imagem principal como loop
            '-i', 'logo.png',                        # Logo como segunda entrada
            '-i', 'musica.mp3',                      # Música como terceira entrada
            '-filter_complex',
            # Efeito de zoom/pan, overlay do logo e overlay do texto
            "[0:v]zoompan=z='min(zoom+0.001,1.1)':d=250:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920[bg];" +
            "[bg][1:v]overlay=70:1500[bg_logo];" +
            f"[bg_logo]drawtext=fontfile=Anton-Regular.ttf:text='{manchete_escapada}':fontcolor=white:fontsize=110:x=(w-text_w)/2:y=1750-text_h:shadowcolor=black:shadowx=5:shadowy=5",
            '-c:v', 'libx264', '-t', '10', '-pix_fmt', 'yuv420p', # Configs de vídeo por 10s
            '-c:a', 'aac', '-shortest', # Configs de áudio
            'output.mp4', '-y' # Arquivo de saída, -y para sobrescrever
        ]
        
        # Executa o comando
        subprocess.run(comando, check=True, capture_output=True, text=True)
        
        # Lê os bytes do vídeo gerado
        with open("output.mp4", "rb") as f:
            video_data = f.read()

        print(f"✅ Vídeo do Reels criado com FFmpeg com sucesso!")
        return video_data

    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao executar FFmpeg:")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return None
    except Exception as e:
        print(f"❌ Erro ao criar vídeo com FFmpeg: {e}")
        return None

def upload_para_wordpress(bytes_video, nome_arquivo):
    print(f"⬆️ Fazendo upload de '{nome_arquivo}' para o WordPress...")
    try:
        url_wp_media = f"{WP_URL}/wp-json/wp/v2/media"
        headers_upload = HEADERS_WP.copy()
        headers_upload['Content-Disposition'] = f'attachment; filename={nome_arquivo}'
        headers_upload['Content-Type'] = 'video/mp4'
        response = requests.post(url_wp_media, headers=headers_upload, data=bytes_video)
        response.raise_for_status()
        link_video_publico = response.json()['source_url']
        print(f"✅ Vídeo salvo na Biblioteca de Mídia! Link: {link_video_publico}")
        return link_video_publico
    except Exception as e:
        print(f"❌ Erro ao fazer upload para o WordPress: {e}")
        return None

def publicar_reels(video_url, legenda, instagram_id):
    print(f"📤 Publicando Reels no Instagram ID: {instagram_id}...")
    if not all([META_API_TOKEN, instagram_id]):
        return f"Publicação pulada (credenciais faltando)."
    try:
        url_container = f"https://graph.facebook.com/v19.0/{instagram_id}/media"
        params_container = {'media_type': 'REELS', 'video_url': video_url, 'caption': legenda, 'access_token': META_API_TOKEN}
        r_container = requests.post(url_container, params=params_container); r_container.raise_for_status()
        id_criacao = r_container.json()['id']
        
        for _ in range(20):
            import time; time.sleep(5)
            url_status = f"https://graph.facebook.com/v19.0/{id_criacao}?fields=status_code&access_token={META_API_TOKEN}"
            r_status = requests.get(url_status); r_status.raise_for_status()
            status = r_status.json().get('status_code')
            print(f"Status do upload: {status}")
            if status == 'FINISHED': break
        
        if status != 'FINISHED': raise Exception("Processamento do vídeo demorou demais.")

        url_publicacao = f"https://graph.facebook.com/v19.0/{instagram_id}/media_publish"
        params_publicacao = {'creation_id': id_criacao, 'access_token': META_API_TOKEN}
        r_publish = requests.post(url_publicacao, params=params_publicacao); r_publish.raise_for_status()
        print(f"✅ Reels publicado no Instagram ID {instagram_id} com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao publicar Reels no Instagram ID {instagram_id}: {e.json()}")
        return False

# ==============================================================================
# BLOCO 4: O MAESTRO (RECEPTOR DO WEBHOOK)
# ==============================================================================
@app.route('/webhook-receiver', methods=['POST'])
def webhook_receiver():
    print("\n\n🔔 Webhook recebido do WordPress!")
    dados_brutos = request.json
    dados_wp = dados_brutos[0] if isinstance(dados_brutos, list) and dados_brutos else dados_brutos
    
    try:
        post_id = dados_wp.get('post_id')
        if not post_id: raise ValueError("Webhook não enviou o ID do post.")

        print(f"🔍 Buscando detalhes do post ID: {post_id}...")
        url_api_post = f"{WP_URL}/wp-json/wp/v2/posts/{post_id}?_embed"
        response_post = requests.get(url_api_post, headers=HEADERS_WP)
        response_post.raise_for_status()
        post_data = response_post.json()

        titulo_noticia = post_data.get('title', {}).get('rendered')
        resumo_noticia = post_data.get('excerpt', {}).get('rendered')
        resumo_noticia = BeautifulSoup(resumo_noticia, 'html.parser').get_text(strip=True)
        url_imagem_destaque = post_data.get('_embedded', {}).get('wp:featuredmedia', [{}])[0].get('source_url')
        
        url_logo = "http://jornalvozdolitoral.com/wp-content/uploads/2025/08/BOCA-NO-TROMBONE-simples.png"
        url_musica = "http://jornalvozdolitoral.com/wp-content/uploads/2025/08/News-Boca-.mp3"
        
        if not url_imagem_destaque:
            raise ValueError("Post não possui Imagem de Destaque.")
            
    except Exception as e:
        print(f"❌ Erro ao processar dados do webhook: {e}")
        return jsonify({"status": "erro"}), 400

    print(f"📰 Notícia recebida: {titulo_noticia}")
    
    video_gerado_bytes = criar_video_reels_com_ffmpeg(url_imagem_destaque, titulo_noticia.upper(), url_logo, url_musica)
    if not video_gerado_bytes: return jsonify({"status": "erro"}), 500
    
    nome_do_arquivo = f"reels_{post_id}.mp4"
    link_wp_video = upload_para_wordpress(video_gerado_bytes, nome_do_arquivo)
    if not link_wp_video: return jsonify({"status": "erro"}), 500

    legenda_final = f"{titulo_noticia}\n\n{resumo_noticia}\n\n#noticias #litoralnorte #brasil"
    
    sucesso_ig = publicar_reels(link_wp_video, legenda_final, BOCA_INSTAGRAM_ID)
    
    if sucesso_ig:
        print("✅ Automação de Reels concluída com sucesso!")
        return jsonify({"status": "sucesso"}), 200
    else:
        return jsonify({"status": "erro"}), 500

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    print("✅ Automação de REELS vFinal (FFmpeg) iniciada!")
    app.run(host='0.0.0.0', port=5001, debug=True)