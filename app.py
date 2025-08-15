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

# --- MENSAGEM DE INICIALIZAÇÃO ---
print("🚀 INICIANDO APLICAÇÃO DE AUTOMAÇÃO v2.2 (Diagnóstico Avançado + Design Corrigido)")

# Configs da Imagem
IMG_WIDTH, IMG_HEIGHT = 1080, 1080

# Configs do WordPress
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')
if all([WP_URL, WP_USER, WP_PASSWORD]):
    credentials = f"{WP_USER}:{WP_PASSWORD}"
    token_wp = b64encode(credentials.encode())
    HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}
    print("✅ [CONFIG] Variáveis do WordPress carregadas.")
else:
    print("❌ [ERRO DE CONFIG] Faltando variáveis de ambiente do WordPress (WP_URL, WP_USER, WP_PASSWORD).")
    HEADERS_WP = {}

# Configs da API do Meta (Facebook/Instagram)
META_API_TOKEN = os.getenv('META_API_TOKEN')
INSTAGRAM_ID = os.getenv('INSTAGRAM_ID')
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID')
if all([META_API_TOKEN, INSTAGRAM_ID, FACEBOOK_PAGE_ID]):
    print("✅ [CONFIG] Variáveis do Facebook/Instagram carregadas.")
else:
    print("⚠️ [AVISO DE CONFIG] Faltando uma ou mais variáveis do Meta. A publicação pode falhar.")

# ==============================================================================
# BLOCO 3: FUNÇÕES AUXILIARES
# ==============================================================================
def criar_imagem_post(url_imagem, titulo_post, url_logo):
    print("🎨 [ETAPA 1/4] Iniciando criação da imagem com o novo design...")
    try:
        # --- Download das imagens ---
        print("   - Baixando imagem da notícia...")
        response_img = requests.get(url_imagem, stream=True, timeout=15); response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        
        print("   - Baixando imagem do logo...")
        response_logo = requests.get(url_logo, stream=True, timeout=15); response_logo.raise_for_status()
        logo = Image.open(io.BytesIO(response_logo.content)).convert("RGBA")

        # --- Definição de cores e fontes ---
        cor_fundo_geral = (255, 255, 255, 255) # Fundo branco
        cor_fundo_texto = "#0d1b2a" # Azul escuro
        cor_vermelha = "#d90429"
        fonte_titulo = ImageFont.truetype("Anton-Regular.ttf", 70)
        fonte_arroba = ImageFont.truetype("Anton-Regular.ttf", 35)

        # --- Montagem da imagem ---
        print("   - Montando o layout base...")
        imagem_final = Image.new('RGBA', (IMG_WIDTH, IMG_HEIGHT), cor_fundo_geral)
        draw = ImageDraw.Draw(imagem_final)

        # Coloca a imagem da notícia no topo
        img_w, img_h = 980, 551
        imagem_noticia_resized = imagem_noticia.resize((img_w, img_h))
        pos_img_x = (IMG_WIDTH - img_w) // 2
        imagem_final.paste(imagem_noticia_resized, (pos_img_x, 50))

        # --- NOVO EFEITO DE DESIGN ---
        # Desenha um retângulo vermelho maior por baixo, para criar o efeito de borda
        raio_arredondado = 40
        offset_sombra = 10
        box_vermelho_coords = [(50 - offset_sombra, 620 - offset_sombra), (IMG_WIDTH - 50 + offset_sombra, IMG_HEIGHT - 50 + offset_sombra)]
        draw.rounded_rectangle(box_vermelho_coords, radius=raio_arredondado + offset_sombra, fill=cor_vermelha)

        # Caixa de texto azul escura arredondada por cima
        box_azul_coords = [(50, 620), (IMG_WIDTH - 50, IMG_HEIGHT - 50)]
        draw.rounded_rectangle(box_azul_coords, radius=raio_arredondado, fill=cor_fundo_texto)
        # --- FIM DO NOVO EFEITO ---

        # Coloca o logo centralizado
        logo.thumbnail((220, 220))
        pos_logo_x = (IMG_WIDTH - logo.width) // 2
        pos_logo_y = 620 - (logo.height // 2)
        imagem_final.paste(logo, (pos_logo_x, pos_logo_y), logo)
        
        # Escreve o texto do título
        print("   - Adicionando texto do título...")
        linhas_texto = textwrap.wrap(titulo_post.upper(), width=25)
        texto_junto = "\n".join(linhas_texto)
        draw.text((IMG_WIDTH / 2, 800), texto_junto, font=fonte_titulo, fill=(255,255,255,255), anchor="mm", align="center")
        
        # Escreve o @ do instagram
        draw.text((IMG_WIDTH / 2, 980), "@VOZDOLITORALNORTE", font=fonte_arroba, fill=(255,255,255,255), anchor="ms", align="center")

        # Salva a imagem em memória
        buffer_saida = io.BytesIO()
        imagem_final.convert('RGB').save(buffer_saida, format='JPEG', quality=95)
        print("✅ [ETAPA 1/4] Imagem criada com sucesso!")
        return buffer_saida.getvalue()
        
    except Exception as e:
        print(f"❌ [ERRO] Falha crítica na criação da imagem: {e}")
        return None

def upload_para_wordpress(bytes_imagem, nome_arquivo):
    print(f"⬆️  [ETAPA 2/4] Fazendo upload de '{nome_arquivo}' para o WordPress...")
    try:
        url_wp_media = f"{WP_URL}/wp-json/wp/v2/media"
        headers_upload = HEADERS_WP.copy()
        headers_upload['Content-Disposition'] = f'attachment; filename={nome_arquivo}'
        headers_upload['Content-Type'] = 'image/jpeg'
        response = requests.post(url_wp_media, headers=headers_upload, data=bytes_imagem, timeout=30)
        response.raise_for_status()
        link_imagem_publica = response.json()['source_url']
        print(f"✅ [ETAPA 2/4] Imagem salva no WordPress! Link: {link_imagem_publica}")
        return link_imagem_publica
    except Exception as e:
        print(f"❌ [ERRO] Falha ao fazer upload para o WordPress: {e}")
        return None

def publicar_no_instagram(url_imagem, legenda):
    print("📤 [ETAPA 3/4] Publicando no Instagram...")
    if not all([META_API_TOKEN, INSTAGRAM_ID]): 
        print("   - Publicação pulada: Faltando variáveis de ambiente do Instagram.")
        return False
    try:
        print("   - Criando contêiner de mídia...")
        url_container = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ID}/media"
        params_container = {'image_url': url_imagem, 'caption': legenda, 'access_token': META_API_TOKEN}
        r_container = requests.post(url_container, params=params_container, timeout=20); r_container.raise_for_status()
        id_criacao = r_container.json()['id']
        print(f"   - Contêiner criado com ID: {id_criacao}")

        print("   - Publicando o contêiner...")
        url_publicacao = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ID}/media_publish"
        params_publicacao = {'creation_id': id_criacao, 'access_token': META_API_TOKEN}
        r_publish = requests.post(url_publicacao, params=params_publicacao, timeout=20); r_publish.raise_for_status()
        
        print("✅ [ETAPA 3/4] Post publicado no Instagram com sucesso!")
        return True
    except Exception as e:
        print(f"❌ [ERRO] Falha ao publicar no Instagram: {e}")
        print(f"   - Resposta da API (se houver): {e.response.text if hasattr(e, 'response') else 'N/A'}")
        return False

def publicar_no_facebook(url_imagem, legenda):
    print("📤 [ETAPA 4/4] Publicando no Facebook...")
    if not all([META_API_TOKEN, FACEBOOK_PAGE_ID]): 
        print("   - Publicação pulada: Faltando variáveis de ambiente do Facebook.")
        return False
    try:
        url_post_foto = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/photos"
        params = {'url': url_imagem, 'message': legenda, 'access_token': META_API_TOKEN}
        r = requests.post(url_post_foto, params=params, timeout=20); r.raise_for_status()
        print("✅ [ETAPA 4/4] Post publicado no Facebook com sucesso!")
        return True
    except Exception as e:
        print(f"❌ [ERRO] Falha ao publicar no Facebook: {e}")
        print(f"   - Resposta da API (se houver): {e.response.text if hasattr(e, 'response') else 'N/A'}")
        return False

# ==============================================================================
# BLOCO 4: O MAESTRO (RECEPTOR DO WEBHOOK)
# ==============================================================================
@app.route('/webhook-receiver', methods=['POST'])
def webhook_receiver():
    print("\n" + "="*50)
    print("🔔 [WEBHOOK] Webhook recebido do WordPress!")
    
    post_data = {}
    try:
        dados_brutos = request.json
        dados_wp = dados_brutos[0] if isinstance(dados_brutos, list) and dados_brutos else dados_brutos
        
        post_id = dados_wp.get('post_id')
        if not post_id: 
            print("❌ [ERRO WEBHOOK] 'post_id' não encontrado no corpo do webhook. Abortando.")
            raise ValueError("Webhook não enviou o ID do post.")

        print(f"✅ [WEBHOOK] ID do post extraído com sucesso: {post_id}")
        
        # --- BLOCO DE DIAGNÓSTICO AVANÇADO ---
        try:
            print(f"🔍 [API WP] Tentando buscar detalhes do post ID: {post_id}...")
            url_api_post = f"{WP_URL}/wp-json/wp/v2/posts/{post_id}"
            print(f"   - URL da API: {url_api_post}")
            response_post = requests.get(url_api_post, headers=HEADERS_WP, timeout=15)
            response_post.raise_for_status() # Isso vai gerar um erro se o status for 4xx ou 5xx
            post_data = response_post.json()
            print("✅ [API WP] Dados do post obtidos com sucesso!")
        except requests.exceptions.HTTPError as http_err:
            print(f"❌ [ERRO HTTP] Falha ao buscar dados no WordPress. Código: {http_err.response.status_code}")
            print(f"   - Resposta: {http_err.response.text}")
            print("   - POSSÍVEL CAUSA: Verifique se WP_USER e WP_PASSWORD (senha de aplicação) estão corretos.")
            return jsonify({"status": "erro_autenticacao_wp"}), 401
        except requests.exceptions.RequestException as req_err:
            print(f"❌ [ERRO DE CONEXÃO] Não foi possível conectar ao WordPress: {req_err}")
            print("   - POSSÍVEL CAUSA: Verifique se a WP_URL está correta ou se há um firewall bloqueando.")
            return jsonify({"status": "erro_conexao_wp"}), 500
        # --- FIM DO BLOCO DE DIAGNÓSTICO ---

        titulo_noticia = BeautifulSoup(post_data.get('title', {}).get('rendered', ''), 'html.parser').get_text()
        resumo_noticia = BeautifulSoup(post_data.get('excerpt', {}).get('rendered', ''), 'html.parser').get_text(strip=True)
        id_imagem_destaque = post_data.get('featured_media')
        url_logo = "http://jornalvozdolitoral.com/wp-content/uploads/2025/08/logo_off_2025.png"
        print(f"   - Título extraído: {titulo_noticia}")

        if id_imagem_destaque and id_imagem_destaque > 0:
            print(f"🖼️ [API WP] Imagem de Destaque ID {id_imagem_destaque} encontrada. Buscando URL...")
            url_api_media = f"{WP_URL}/wp-json/wp/v2/media/{id_imagem_destaque}"
            response_media = requests.get(url_api_media, headers=HEADERS_WP, timeout=15); response_media.raise_for_status()
            media_data = response_media.json()
            
            url_imagem_destaque = media_data.get('media_details', {}).get('sizes', {}).get('full', {}).get('source_url')
            if not url_imagem_destaque: url_imagem_destaque = media_data.get('source_url')
            print(f"   - URL da Imagem: {url_imagem_destaque}")
        else:
            print("⚠️ [API WP] Imagem de Destaque não definida. Usando o logo como imagem principal.")
            url_imagem_destaque = url_logo
            
    except Exception as e:
        print(f"❌ [ERRO CRÍTICO INESPERADO] Falha no processamento: {e}")
        return jsonify({"status": "erro_geral"}), 500

    # --- Início do fluxo de publicação ---
    print("\n🚀 INICIANDO FLUXO DE PUBLICAÇÃO NAS REDES SOCIAIS...")
    
    imagem_gerada_bytes = criar_imagem_post(url_imagem_destaque, titulo_noticia, url_logo)
    if not imagem_gerada_bytes: return jsonify({"status": "erro_criacao_imagem"}), 500
    
    nome_do_arquivo = f"post_social_{post_id}.jpg"
    link_wp = upload_para_wordpress(imagem_gerada_bytes, nome_do_arquivo)
    if not link_wp: return jsonify({"status": "erro_upload_wordpress"}), 500

    legenda_final = f"{titulo_noticia}\n\n{resumo_noticia}\n\nLeia a matéria completa em nosso site. Link na bio!\n\n#noticias #litoralnorte #brasil #jornalismo"
    
    sucesso_ig = publicar_no_instagram(link_wp, legenda_final)
    sucesso_fb = publicar_no_facebook(link_wp, legenda_final)

    if sucesso_ig or sucesso_fb:
        print("🎉 [SUCESSO] Automação concluída com sucesso!")
        return jsonify({"status": "sucesso_publicacao"}), 200
    else:
        print("😭 [FALHA] Nenhuma publicação foi bem-sucedida.")
        return jsonify({"status": "erro_publicacao_redes"}), 500

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
@app.route('/')
def health_check():
    return "Serviço de automação v2.2 está no ar.", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
