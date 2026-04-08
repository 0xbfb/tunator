# Tunator

Tunator é um painel local para simplificar o uso do Tor sem depender do serviço do sistema operacional.

Nesta versão ele já vem com:

- backend FastAPI
- interface web já buildada e servida pelo próprio backend
- tela de status, `torrc`, onion services, logs e diagnóstico
- runtime local do Tor dentro do projeto
- criação guiada de onion services com pasta automática e mapeamento de porta

## Como usar no Windows

### 1. Bootstrap do backend

```powershell
cd tunator
powershell -ExecutionPolicy Bypass -File .\scriptsootstrap_backend.ps1
```

### 2. Subir a API + interface

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Agora abre:

- Interface: `http://127.0.0.1:8000/`
- Swagger: `http://127.0.0.1:8000/docs`

## Fluxo de uso

1. abra a interface em `http://127.0.0.1:8000/`
2. veja se o binário local do Tor foi detectado
3. ajuste `SOCKSPort`, `ControlPort`, `DataDirectory` e `Log` se quiser
4. clique em **Salvar torrc**
5. crie um onion informando:
   - nome da pasta
   - porta pública do onion, tipo `80`
   - host interno, tipo `127.0.0.1`
   - porta interna da sua app, tipo `3000`
6. clique em **Criar onion**
7. clique em **Iniciar** ou **Reiniciar Tor**
8. depois leia o arquivo `hostname` dentro da pasta do onion criada

## Exemplo prático

Se sua aplicação local está em `127.0.0.1:3000`, crie assim:

- Nome da pasta: `meu-site`
- Porta pública: `80`
- Host interno: `127.0.0.1`
- Porta interna: `3000`

Isso gera algo equivalente a:

```torrc
HiddenServiceDir .../backend/vendor/tor/state/onions/meu-site
HiddenServicePort 80 127.0.0.1:3000
```

Depois que o Tor subir, o endereço `.onion` aparece em:

```text
backend/vendor/tor/state/onions/meu-site/hostname
```

## Observações úteis

- A interface edita só o núcleo do `torrc` e os blocos de onion service. Isso foi de propósito.
- Se você quiser desenvolver a UI, ainda dá pra usar `frontend/` com `npm install && npm run dev`, mas não precisa pra usar o projeto.
- O backend serve a UI buildada automaticamente quando `frontend/dist` existe, e esse zip já inclui isso.
