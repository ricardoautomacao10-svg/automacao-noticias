# ==============================================================================
# BLOCO 1: IMPORTAÇÕES
# ==============================================================================
import os
import io
import json
import requests
import textwrap
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from base64 import b64encode
from moviepy.editor import *
import numpy as np

# ==============================================================================
# BLOCO 2: CONFIGURAÇÃO INICIAL
# ==============================================================================
load_dotenv()
app = Flask(__name__)

# Configs do WordPress
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}

# Configs da API do Meta
META_API_TOKEN = os.getenv('META_API_TOKEN')
BOCA_INSTAGRAM_ID = os.getenv('BOCA_INSTAGRAM_ID')
BOCA_FACEBOOK_PAGE_ID = os.getenv('BOCA_FACEBOOK_PAGE_ID')

# ==============================================================================
# BLOCO 3: FUNÇÕES AUXILIARES
# ==============================================================================
def gerar_manchete_com_ia(titulo, texto_noticia):
    print("🤖 Conectando com a IA para gerar manchete...")
    # (Usaremos o resumo do post do WP por ser mais direto e confiável)
    resumo = BeautifulSoup(texto_noticia, 'html.parser').get_text(strip=True)[:200]
    manchete = titulo.upper() # Usaremos o título original em maiúsculas para o vídeo
    print("✅ Manchete e resumo definidos.")
    return {"manchete": manchete, "resumo": resumo}

def criar_video_reels(url_imagem, manchete, url_logo, url_musica):
    print(f"🎬 Começando a criação do vídeo para o Reels...")
    try:
        # Download dos assets
        response_img = requests.get(url_imagem, stream=True); response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content))

        response_logo = requests.get(url_logo, stream=True); response_logo.raise_for_status()
        logo = Image.open(io.BytesIO(response_logo.content)).convert("RGBA")

        # Preparar a imagem base com o design
        fundo = Image.new('RGB', (1080, 1920), (0,0,0))
        
        # Redimensiona a imagem para preencher a largura e corta na altura
        img_w, img_h = imagem_noticia.size
        ratio = img_h / img_w
        new_w = 1080
        new_h = int(new_w * ratio)
        imagem_noticia = imagem_noticia.resize((new_w, new_h))
        
        corte_y = (new_h - 1920) // 2
        imagem_final = imagem_noticia.crop((0, corte_y, 1080, corte_y + 1920))
        
        fundo.paste(imagem_final, (0,0))
        
        # Adiciona sobreposições (logo, texto, etc.)
        draw = ImageDraw.Draw(fundo)
        fonte_manchete = ImageFont.truetype("Anton-Regular.ttf", 110)
        
        logo.thumbnail((250, 250))
        fundo.paste(logo, (70, 1500), logo)

        linhas_texto = textwrap.wrap(manchete, width=18)
        texto_junto = "\n".join(linhas_texto)
        draw.text((540, 1750), texto_junto, font=fonte_manchete, fill=(255,255,255,255), anchor="ms", align="center", stroke_width=5, stroke_fill=(0,0,0))

        # Converte a imagem PIL para um clipe de vídeo
        clip = ImageClip(np.array(fundo)).set_duration(10)
        
        # Efeito Pan e Zoom (Ken Burns)
        clip_zoomed = clip.resize(lambda t: 1 + 0.02 * t).set_position(('center', 'center'))
        final_clip = CompositeVideoClip([clip_zoomed], size=(1080,1920)).set_duration(10)

        # Adiciona a música
        audio_clip = AudioFileClip(url_musica).set_duration(10)
        final_video = final_clip.set_audio(audio_clip)

        # Salva o vídeo em um arquivo temporário em memória
        video_bytes = final_video.write_videofile("temp_video.mp4", codec="libx264", audio_codec="aac", temp_audiofile='temp-audio.m4a', remove_temp=True)
        
        # Lê os bytes do arquivo de vídeo salvo para retornar
        with open("temp_video.mp4", "rb") as f:
            video_data = f.read()

        print(f"✅ Vídeo do Reels criado com sucesso!")
        return video_data

    except Exception as e:
        print(f"❌ Erro ao criar vídeo com MoviePy: {e}")
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
        return f"Publicação pulada (credenciais faltando para ID {instagram_id})."
    
    try:
        # Passo 1: Iniciar o upload
        url_container = f"https://graph.facebook.com/v19.0/{instagram_id}/media"
        params_container = {
            'media_type': 'REELS',
            'video_url': video_url,
            'caption': legenda,
            'access_token': META_API_TOKEN
        }
        r_container = requests.post(url_container, params=params_container); r_container.raise_for_status()
        id_criacao = r_container.json()['id']
        
        # Passo 2: Aguardar o vídeo ser processado
        for _ in range(20): # Tenta por até 100 segundos
            import time
            time.sleep(5)
            url_status = f"https://graph.facebook.com/v19.0/{id_criacao}"
            params_status = {'fields': 'status_code', 'access_token': META_API_TOKEN}
            r_status = requests.get(url_status, params=params_status); r_status.raise_for_status()
            status = r_status.json().get('status_code')
            print(f"Status do upload: {status}")
            if status == 'FINISHED':
                break
        
        if status != 'FINISHED':
            raise Exception("Processamento do vídeo demorou demais.")

        # Passo 3: Publicar o container
        url_publicacao = f"https://graph.facebook.com/v19.0/{instagram_id}/media_publish"
        params_publicacao = {'creation_id': id_criacao, 'access_token': META_API_TOKEN}
        r_publish = requests.post(url_publicacao, params=params_publicacao); r_publish.raise_for_status()
        
        print(f"✅ Reels publicado no Instagram ID {instagram_id} com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao publicar Reels no Instagram ID {instagram_id}: {e}")
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
            raise ValueError("Post não possui Imagem de Destaque, não é possível criar o vídeo.")
            
    except Exception as e:
        print(f"❌ Erro ao processar dados do webhook: {e}")
        return jsonify({"status": "erro", "mensagem": "Falha ao buscar dados do post."}), 400

    print(f"📰 Notícia recebida: {titulo_noticia}")
    
    conteudo_ia = gerar_manchete_com_ia(titulo_noticia, resumo_noticia)
    
    video_gerado_bytes = criar_video_reels(url_imagem_destaque, conteudo_ia['manchete'], url_logo, url_musica)
    if not video_gerado_bytes: return jsonify({"status": "erro", "mensagem": "Falha na criação do vídeo."}), 500
    
    nome_do_arquivo = f"reels_{post_id}.mp4"
    link_wp_video = upload_para_wordpress(video_gerado_bytes, nome_do_arquivo)
    if not link_wp_video: return jsonify({"status": "erro", "mensagem": "Falha no upload para o WordPress."}), 500

    legenda_final = f"{titulo_noticia}\n\n{conteudo_ia['resumo']}\n\n#noticias #litoralnorte #brasil"
    
    # Publica no Instagram do Boca no Trombone
    sucesso_ig = publicar_reels(link_wp_video, legenda_final, BOCA_INSTAGRAM_ID)
    
    # (A publicação de Reels no Facebook é mais complexa e usa um endpoint diferente, vamos focar no Instagram primeiro)

    if sucesso_ig:
        print("✅ Automação de Reels concluída com sucesso!")
        return jsonify({"status": "sucesso"}), 200
    else:
        return jsonify({"status": "erro", "mensagem": "Falha ao publicar o Reels."}), 500

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    print("✅ Automação de REELS iniciada!")
    app.run(host='0.0.0.0', port=5001, debug=True)