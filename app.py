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

# ==============================================================================
# BLOCO 2: CONFIGURAÇÃO INICIAL
# ==============================================================================
load_dotenv()
app = Flask(__name__)

# Configs da Imagem
IMG_WIDTH, IMG_HEIGHT = 1080, 1080

# Configs do WordPress
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}

# Configs da API do Meta (Facebook/Instagram)
META_API_TOKEN = os.getenv('META_API_TOKEN')
INSTAGRAM_ID = os.getenv('INSTAGRAM_ID')
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID')

# ==============================================================================
# BLOCO 3: FUNÇÕES AUXILIARES
# ==============================================================================
def criar_imagem_post(url_imagem, titulo_post, url_logo):
    print(f"🎨 Começando a criação da imagem com o design final...")
    try:
        response_img = requests.get(url_imagem, stream=True); response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        
        response_logo = requests.get(url_logo, stream=True); response_logo.raise_for_status()
        logo = Image.open(io.BytesIO(response_logo.content)).convert("RGBA")
        
        cor_fundo = "#051d40"
        fundo = Image.new('RGBA', (IMG_WIDTH, IMG_HEIGHT), cor_fundo)
        draw = ImageDraw.Draw(fundo)
        
        fonte_titulo = ImageFont.truetype("Anton-Regular.ttf", 60)
        fonte_cta = ImageFont.truetype("Anton-Regular.ttf", 32)
        fonte_site = ImageFont.truetype("Anton-Regular.ttf", 28)

        img_w, img_h = 980, 551
        imagem_noticia_resized = imagem_noticia.resize((img_w, img_h))
        pos_img_x = (IMG_WIDTH - img_w) // 2
        fundo.paste(imagem_noticia_resized, (pos_img_x, 50))
        
        logo.thumbnail((180, 180))
        fundo.paste(logo, (pos_img_x + 20, 50 + 20), logo)
        
        linhas_texto = textwrap.wrap(titulo_post, width=35)
        texto_junto = "\n".join(linhas_texto)
        draw.text((IMG_WIDTH / 2, 700), texto_junto, font=fonte_titulo, fill=(255,255,255,255), anchor="ma", align="center")
        
        texto_rodape = "LEIA MAIS: jornalvozdolitoral.com"
        draw.text((IMG_WIDTH / 2, 980), texto_rodape, font=fonte_cta, fill=(255,255,255,255), anchor="ms", align="center")
        
        buffer_saida = io.BytesIO()
        fundo.save(buffer_saida, format='PNG')
        print(f"✅ Imagem com novo design criada com sucesso!")
        return buffer_saida.getvalue()
    except Exception as e:
        print(f"❌ Erro ao criar imagem com Pillow: {e}")
        return None

def upload_para_wordpress(bytes_imagem, nome_arquivo):
    print(f"⬆️ Fazendo upload de '{nome_arquivo}' para o WordPress...")
    try:
        url_wp_media = f"{WP_URL}/wp-json/wp/v2/media"
        headers_upload = HEADERS_WP.copy()
        headers_upload['Content-Disposition'] = f'attachment; filename={nome_arquivo}'
        headers_upload['Content-Type'] = 'image/png'
        response = requests.post(url_wp_media, headers=headers_upload, data=bytes_imagem)
        response.raise_for_status()
        link_imagem_publica = response.json()['source_url']
        print(f"✅ Imagem salva na Biblioteca de Mídia! Link: {link_imagem_publica}")
        return link_imagem_publica
    except Exception as e:
        print(f"❌ Erro ao fazer upload para o WordPress: {e}")
        return None

def publicar_no_instagram(url_imagem, legenda):
    print("📤 Publicando no Instagram...")
    if not all([META_API_TOKEN, INSTAGRAM_ID]):
        return "Publicação no Instagram pulada (credenciais faltando)."
    try:
        url_container = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ID}/media"
        params_container = {'image_url': url_imagem, 'caption': legenda, 'access_token': META_API_TOKEN}
        r_container = requests.post(url_container, params=params_container); r_container.raise_for_status()
        id_criacao = r_container.json()['id']
        
        url_publicacao = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ID}/media_publish"
        params_publicacao = {'creation_id': id_criacao, 'access_token': META_API_TOKEN}
        r_publish = requests.post(url_publicacao, params=params_publicacao); r_publish.raise_for_status()
        
        print("✅ Post publicado no Instagram com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao publicar no Instagram: {e}")
        return False

def publicar_no_facebook(url_imagem, legenda):
    print("📤 Publicando no Facebook...")
    if not all([META_API_TOKEN, FACEBOOK_PAGE_ID]):
        return "Publicação no Facebook pulada (credenciais faltando)."
    try:
        url_post_foto = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/photos"
        params = {'url': url_imagem, 'message': legenda, 'access_token': META_API_TOKEN}
        r = requests.post(url_post_foto, params=params); r.raise_for_status()
        
        print("✅ Post publicado na Página do Facebook com sucesso!")
        return True
    except Exception as e:
        print(f"❌ Erro ao publicar no Facebook: {e}")
        return False

# ==============================================================================
# BLOCO 4: O MAESTRO (RECEPTOR DO WEBHOOK) - VERSÃO À PROVA DE FALHAS v7.0
# ==============================================================================
@app.route('/webhook-receiver', methods=['POST'])
def webhook_receiver():
    print("\n\n🔔 Webhook recebido do WordPress!")
    dados_brutos = request.json
    dados_wp = dados_brutos[0] if isinstance(dados_brutos, list) and dados_brutos else dados_brutos
    
    try:
        post_id = dados_wp.get('post_id')
        if not post_id:
            raise ValueError("Webhook não enviou o ID do post.")

        # --- NOVA LÓGICA INTELIGENTE v7.0 ---
        print(f"🔍 Buscando detalhes do post ID: {post_id} diretamente no WordPress...")
        url_api_post = f"{WP_URL}/wp-json/wp/v2/posts/{post_id}"
        response_post = requests.get(url_api_post, headers=HEADERS_WP)
        response_post.raise_for_status()
        post_data = response_post.json()

        titulo_noticia = post_data.get('title', {}).get('rendered')
        resumo_noticia = post_data.get('excerpt', {}).get('rendered')
        resumo_noticia = BeautifulSoup(resumo_noticia, 'html.parser').get_text(strip=True)
        
        # Busca o ID da imagem de destaque
        id_imagem_destaque = post_data.get('featured_media')
        url_logo = "http://jornalvozdolitoral.com/wp-content/uploads/2025/08/logo_off_2025.png"

        if id_imagem_destaque and id_imagem_destaque > 0:
            print(f"🖼️ Imagem de Destaque ID {id_imagem_destaque} encontrada. Buscando URL...")
            url_api_media = f"{WP_URL}/wp-json/wp/v2/media/{id_imagem_destaque}"
            response_media = requests.get(url_api_media, headers=HEADERS_WP)
            response_media.raise_for_status()
            media_data = response_media.json()
            url_imagem_destaque = media_data.get('source_url')
            print(f"✅ URL da Imagem de Destaque: {url_imagem_destaque}")
        else:
            print(f"⚠️ Imagem de Destaque não definida para o post. Usando o logo como imagem principal.")
            url_imagem_destaque = url_logo

        if not all([titulo_noticia, resumo_noticia]):
            raise ValueError("Não foi possível extrair título ou resumo do post via API.")
            
    except Exception as e:
        print(f"❌ Erro ao processar dados do webhook: {e}")
        return jsonify({"status": "erro", "mensagem": "Falha ao buscar dados do post no WordPress."}), 400

    print(f"📰 Notícia recebida: {titulo_noticia}")
    
    imagem_gerada_bytes = criar_imagem_post(url_imagem_destaque, titulo_noticia, url_logo)
    if not imagem_gerada_bytes: return jsonify({"status": "erro", "mensagem": "Falha na criação da imagem."}), 500
    
    nome_do_arquivo = f"post_{post_id}.png"
    link_wp = upload_para_wordpress(imagem_gerada_bytes, nome_do_arquivo)
    if not link_wp: return jsonify({"status": "erro", "mensagem": "Falha no upload para o WordPress."}), 500

    legenda_final = f"{titulo_noticia}\n\n{resumo_noticia}\n\nLeia a matéria completa em nosso site. Link na bio!\n\n#noticias #litoralnorte #brasil #jornalismo"
    
    sucesso_ig = publicar_no_instagram(link_wp, legenda_final)
    sucesso_fb = publicar_no_facebook(link_wp, legenda_final)

    if sucesso_ig or sucesso_fb:
        print("✅ Automação concluída
