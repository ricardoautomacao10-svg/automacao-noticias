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
import redis

# ==============================================================================
# BLOCO 2: CONFIGURAÇÃO INICIAL
# ==============================================================================
load_dotenv()
app = Flask(__name__)

# --- MEMÓRIA PERMANENTE ANTI-DUPLICAÇÃO ---
try:
    REDIS_URL = os.getenv('REDIS_URL')
    if not REDIS_URL:
        raise ValueError("URL do Redis não encontrada.")
    memoria_de_posts = redis.from_url(REDIS_URL, decode_responses=True)
    print("✅ Conectado à memória permanente (Redis) com sucesso!")
except Exception as e:
    print(f"❌ AVISO: Não foi possível conectar à memória permanente (Redis). Erro: {e}")
    memoria_de_posts = None

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
    print(f"🎨 Começando a criação da imagem com o novo design...")
    try:
        # --- Download dos assets ---
        response_img = requests.get(url_imagem, stream=True); response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        
        response_logo = requests.get(url_logo, stream=True); response_logo.raise_for_status()
        logo = Image.open(io.BytesIO(response_logo.content)).convert("RGBA")

        # --- Preparação da tela e cores ---
        cor_fundo_geral = (230, 230, 230, 255) # Um cinza claro para o fundo
        cor_fundo_texto = "#0d1b2a" # Azul escuro do seu modelo
        cor_vermelha = "#d90429"
        
        imagem_final = Image.new('RGBA', (IMG_WIDTH, IMG_HEIGHT), cor_fundo_geral)
        draw = ImageDraw.Draw(imagem_final)

        # --- Desenho dos elementos ---
        # 1. Imagem da notícia no topo
        img_w, img_h = 980, 551 # Proporção 16:9
        imagem_noticia_resized = imagem_noticia.resize((img_w, img_h))
        pos_img_x = (IMG_WIDTH - img_w) // 2
        imagem_final.paste(imagem_noticia_resized, (pos_img_x, 50))

        # 2. Logo no meio
        logo.thumbnail((200, 200))
        pos_logo_x = (IMG_WIDTH - logo.width) // 2
        pos_logo_y = 550 - (logo.height // 2) # Centralizado na transição
        imagem_final.paste(logo, (pos_logo_x, pos_logo_y), logo)

        # 3. Bloco de texto azul
        raio_arredondado = 40
        # Coordenadas do retângulo azul
        box_azul_coords = [(50, 620), (IMG_WIDTH - 50, IMG_HEIGHT - 50)]
        draw.rounded_rectangle(box_azul_coords, radius=raio_arredondado, fill=cor_fundo_texto)

        # 4. Detalhes decorativos (curvas)
        # Curva vermelha
        draw.arc([(20, 580), (200, 660)], start=-90, end=0, fill=cor_vermelha, width=15)
        # Curva branca
        draw.arc([(IMG_WIDTH - 200, 580), (IMG_WIDTH - 20, 660)], start=180, end=270, fill="#FFFFFF", width=15)

        # 5. Textos
        fonte_titulo = ImageFont.truetype("Anton-Regular.ttf", 80)
        fonte_arroba = ImageFont.truetype("Anton-Regular.ttf", 40)

        # Título
        linhas_texto = textwrap.wrap(titulo_post.upper(), width=22)
        texto_junto = "\n".join(linhas_texto)
        draw.text((IMG_WIDTH / 2, 800), texto_junto, font=fonte_titulo, fill=(255,255,255,255), anchor="mm", align="center")
        
        # Arroba
        draw.text((IMG_WIDTH / 2, 980), "@VOZDOLITORALNORTE", font=fonte_arroba, fill=(255,255,255,255), anchor="ms", align="center")

        # --- Finalização ---
        buffer_saida = io.BytesIO()
        imagem_final.save(buffer_saida, format='PNG')
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
    if not all([META_API_TOKEN, INSTAGRAM_ID]): return "Publicação pulada."
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
    if not all([META_API_TOKEN, FACEBOOK_PAGE_ID]): return "Publicação pulada."
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

        if memoria_de_posts is not None:
            chave_redis = f"post:{post_id}"
            if not memoria_de_posts.set(chave_redis, "processado", ex=86400, nx=True):
                print(f"⚠️ Post ID {post_id} já foi processado. Ignorando duplicata.")
                return jsonify({"status": "duplicado"}), 200
        
        print(f"🔍 Buscando detalhes do post ID: {post_id} via API...")
        url_api_post = f"{WP_URL}/wp-json/wp/v2/posts/{post_id}"
        response_post = requests.get(url_api_post, headers=HEADERS_WP); response_post.raise_for_status()
        post_data = response_post.json()

        titulo_noticia = BeautifulSoup(post_data.get('title', {}).get('rendered'), 'html.parser').get_text()
        resumo_noticia = BeautifulSoup(post_data.get('excerpt', {}).get('rendered'), 'html.parser').get_text(strip=True)
        
        id_imagem_destaque = post_data.get('featured_media')
        url_logo = "http://jornalvozdolitoral.com/wp-content/uploads/2025/08/logo_off_2025.png"

        if id_imagem_destaque and id_imagem_destaque > 0:
            print(f"🖼️ Imagem de Destaque ID {id_imagem_destaque} encontrada. Buscando URL...")
            url_api_media = f"{WP_URL}/wp-json/wp/v2/media/{id_imagem_destaque}"
            response_media = requests.get(url_api_media, headers=HEADERS_WP); response_media.raise_for_status()
            media_data = response_media.json()
            
            url_imagem_destaque = media_data.get('media_details', {}).get('sizes', {}).get('full', {}).get('source_url')
            if not url_imagem_destaque: url_imagem_destaque = media_data.get('source_url')
            print(f"✅ URL da Imagem de Destaque (Tamanho Completo): {url_imagem_destaque}")
        else:
            print(f"⚠️ Imagem de Destaque não definida. Usando o logo como imagem principal.")
            url_imagem_destaque = url_logo
            
    except Exception as e:
        print(f"❌ Erro ao processar dados do webhook: {e}")
        return jsonify({"status": "erro"}), 400

    print(f"📰 Notícia recebida: {titulo_noticia}")
    
    imagem_gerada_bytes = criar_imagem_post(url_imagem_destaque, titulo_noticia, url_logo)
    if not imagem_gerada_bytes: return jsonify({"status": "erro"}), 500
    
    nome_do_arquivo = f"post_{post_id}.png"
    link_wp = upload_para_wordpress(imagem_gerada_bytes, nome_do_arquivo)
    if not link_wp: return jsonify({"status": "erro"}), 500

    legenda_final = f"{titulo_noticia}\n\n{resumo_noticia}\n\nLeia a matéria completa em nosso site. Link na bio!\n\n#noticias #litoralnorte #brasil #jornalismo"
    
    sucesso_ig = publicar_no_instagram(link_wp, legenda_final)
    sucesso_fb = publicar_no_facebook(link_wp, legenda_final)

    if sucesso_ig or sucesso_fb:
        print("✅ Automação concluída com sucesso!")
        return jsonify({"status": "sucesso"}), 200
    else:
        return jsonify({"status": "erro"}), 500

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    print("✅ Automação Final Estável (v18 - Novo Design).")
    app.run(host='0.0.0.0', port=5001, debug=True)
