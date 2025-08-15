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
    if not REDIS_URL: raise ValueError("URL do Redis não encontrada.")
    memoria_de_posts = redis.from_url(REDIS_URL, decode_responses=True)
    print("✅ Conectado à memória permanente (Redis) com sucesso!")
except Exception as e:
    print(f"❌ AVISO: Não foi possível conectar à memória permanente (Redis). Erro: {e}")
    memoria_de_posts = None

# Configs da IA
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")
API_URL_INSTRUCT = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
HEADERS_HF = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}

# Configs da Imagem
IMG_WIDTH, IMG_HEIGHT = 1080, 1080

# Configs do WordPress
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}

# Configs da API do Meta
META_API_TOKEN = os.getenv('META_API_TOKEN')
INSTAGRAM_ID = os.getenv('INSTAGRAM_ID')
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID')

# ==============================================================================
# BLOCO 3: FUNÇÕES AUXILIARES
# ==============================================================================
def gerar_conteudo_com_ia(titulo, texto_noticia):
    print("🤖 Conectando com a IA para gerar legenda e hashtags...")
    if not HUGGINGFACE_TOKEN:
        print("⚠️ Token da Hugging Face não configurado. Usando Plano B.")
        return None

    prompt = f"""
[INST]
# PERSONA E CONTEXTO
Você é um social media manager especialista em jornalismo comunitário para o Litoral Norte de São Paulo. Sua habilidade é "traduzir" artigos de portal em posts curtos, impactantes e que geram conversas no Facebook e Instagram.

# DIRETRIZES OBRIGATÓRIAS
1. Foco no Impacto Humano: Ignore detalhes burocráticos e foque em como a notícia afeta a vida das pessoas.
2. Linguagem de Rede Social: Use uma linguagem informal, direta e conversacional. Use quebras de linha para facilitar a leitura.
3. Engajamento é Rei: Termine sempre com uma pergunta aberta para estimular os comentários.

# TAREFA
Com base no artigo completo fornecido, gere uma resposta ESTRITAMENTE no formato JSON abaixo, sem nenhum texto antes ou depois:
{{
 "legenda": "[Comece com um emoji relevante e uma frase de impacto que resuma a notícia.]\\n\\n[Desenvolva a informação em 1 ou 2 parágrafos curtos.]\\n\\nTodos os detalhes estão na matéria completa em nosso portal. Link na bio!\\n\\n[Termine com uma pergunta aberta e direta para o leitor. Ex: 'E aí, o que você achou dessa mudança? Conta pra gente! 👇']",
 "hashtags": "[#CidadePrincipal] [#LitoralNorteSP] [#TemaDaNoticia1] [#TemaDaNoticia2] #[JornalVozDoLitoral]"
}}

# TEXTO COMPLETO DO ARTIGO DO PORTAL
{texto_noticia[:2000]}
[/INST]
"""
    
    try:
        payload = {"inputs": prompt, "parameters": {"max_new_tokens": 400, "return_full_text": False}}
        response = requests.post(API_URL_INSTRUCT, headers=HEADERS_HF, json=payload)
        response.raise_for_status()
        
        resultado_texto = response.json()[0]['generated_text']
        json_str = '{' + resultado_texto.split('{', 1)[-1].rsplit('}', 1)[0] + '}'
        
        conteudo_gerado = json.loads(json_str)
        print("✅ Conteúdo completo (legenda e hashtags) gerado pela IA!")
        return conteudo_gerado
        
    except Exception as e:
        print(f"❌ Erro na IA da Hugging Face: {e}. Usando Plano B.")
        return None

def criar_imagem_post(url_imagem, titulo_post, url_logo):
    print(f"🎨 Começando a criação da imagem com o design final...")
    try:
        response_img = requests.get(url_imagem, stream=True); response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        
        response_logo = requests.get(url_logo, stream=True); response_logo.raise_for_status()
        logo = Image.open(io.BytesIO(response_logo.content)).convert("RGBA")
        
        cor_fundo = "#051d40"; fundo = Image.new('RGBA', (IMG_WIDTH, IMG_HEIGHT), cor_fundo)
        draw = ImageDraw.Draw(fundo)
        
        fonte_titulo = ImageFont.truetype("Raleway-VariableFont_wght.ttf", 60, layout_engine=ImageFont.Layout.RAQM, features=['-kern'], variation_settings={'wght': 800})
        fonte_cta = ImageFont.truetype("Raleway-VariableFont_wght.ttf", 32, layout_engine=ImageFont.Layout.RAQM, features=['-kern'], variation_settings={'wght': 700})
        fonte_site = ImageFont.truetype("Raleway-VariableFont_wght.ttf", 28, layout_engine=ImageFont.Layout.RAQM, features=['-kern'], variation_settings={'wght': 500})

        img_w, img_h = 980, 551
        imagem_noticia_resized = imagem_noticia.resize((img_w, img_h))
        pos_img_x = (IMG_WIDTH - img_w) // 2
        fundo.paste(imagem_noticia_resized, (pos_img_x, 50))
        logo.thumbnail((180, 180)); fundo.paste(logo, (pos_img_x + 20, 50 + 20), logo)
        
        linhas_texto = textwrap.wrap(titulo_post.upper(), width=35)
        texto_junto = "\n".join(linhas_texto)
        draw.text((IMG_WIDTH / 2, 700), texto_junto, font=fonte_titulo, fill=(255,255,255,255), anchor="ma", align="center")
        
        texto_cta = "LEIA MAIS:"
        texto_site = " jornalvozdolitoral.com"
        largura_cta = draw.textlength(texto_cta, font=fonte_cta)
        largura_site = draw.textlength(texto_site, font=fonte_site)
        largura_total = largura_cta + largura_site
        pos_inicial_x = (IMG_WIDTH - largura_total) / 2
        pos_y = 980
        draw.text((pos_inicial_x, pos_y), texto_cta, font=fonte_cta, fill="#FF0000", anchor="ls")
        draw.text((pos_inicial_x + largura_cta, pos_y), texto_site, font=fonte_site, fill=(255,255,255,255), anchor="ls")

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
        texto_completo = BeautifulSoup(post_data.get('content', {}).get('rendered'), 'html.parser').get_text(strip=True)
        
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
    
    # Tenta usar a IA (Plano A)
    conteudo_ia = gerar_conteudo_com_ia(titulo_noticia, texto_completo)
    
    # Monta a legenda final
    if conteudo_ia and 'legenda' in conteudo_ia and 'hashtags' in conteudo_ia:
        # Plano A: Usa o texto da IA
        legenda_final = f"{conteudo_ia['legenda']}\n\n{conteudo_ia['hashtags']}"
    else:
        # Plano B: Usa o texto padrão do WordPress
        print("🔧 Montando legenda com o Plano B (texto do WordPress).")
        legenda_final = f"{titulo_noticia}\n\n{resumo_noticia}\n\nLeia a matéria completa em nosso site. Link na bio!\n\n#noticias #litoralnorte #brasil #jornalismo"

    imagem_gerada_bytes = criar_imagem_post(url_imagem_destaque, titulo_noticia, url_logo)
    if not imagem_gerada_bytes: return jsonify({"status": "erro"}), 500
    
    nome_do_arquivo = f"post_{post_id}.png"
    link_wp = upload_para_wordpress(imagem_gerada_bytes, nome_do_arquivo)
    if not link_wp: return jsonify({"status": "erro"}), 500
    
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
    print("✅ Automação Final Estável (v19 - IA com Fallback).")
    app.run(host='0.0.0.0', port=5001, debug=True)
```

### O Que Fazer Agora

1.  **Verifique a Chave no Render:** Vá na aba "Environment" do seu serviço no Render e garanta que a variável `HUGGINGFACE_TOKEN` existe e está com a sua chave correta (aquela com permissão de `write`).
2.  **Substitua o código** do seu `app.py` por esta nova versão.
3.  **Envie** o arquivo `app.py` atualizado para o **GitHub**.
4.  **Aguarde** o deploy no Render.
5.  **Teste** com um novo post.
