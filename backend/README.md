# Tunator

Tunator é um painel local para simplificar o uso do Tor sem depender do serviço de sistema operacional.

Ele reúne em um só lugar:

- backend em **FastAPI**
- interface web servida pelo próprio backend
- gerenciamento de `torrc`
- criação de **Onion Services**
- leitura de logs e diagnóstico de ambiente
- runtime local do Tor dentro do projeto

---

## Requisitos

- **Python 3.12+**
- **Node.js 20+** (opcional, apenas para desenvolvimento da UI)
- **Windows, Linux ou macOS**

> O projeto foi pensado para rodar localmente. Não exponha esta API diretamente na internet.

---

## Estrutura do projeto

```text
tunator/
├─ backend/                 # API FastAPI + regras de negócio
├─ frontend/                # UI (Vue + Vite)
├─ scripts/                 # scripts de bootstrap
├─ docker/                  # docker-compose para desenvolvimento
└─ docs/                    # documentação adicional
```

---

## Setup rápido

### Windows (PowerShell)

```powershell
cd tunator
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_backend.ps1
```

### Linux/macOS (bash)

```bash
cd tunator
bash ./scripts/bootstrap_backend.sh
```

Os scripts fazem:

1. criação de `backend/.venv`
2. instalação de dependências do backend (`-e .[dev]`)
3. bootstrap do runtime local do Tor (`bootstrap-local-tor`)

---

## Rodando a aplicação

```bash
cd backend
# Windows: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
uvicorn app.main:app --reload --reload-exclude "vendor/tor/state/*" --reload-exclude "tunator.db"
```

Com a API no ar:

- Interface: <http://127.0.0.1:8000/>
- OpenAPI/Swagger: <http://127.0.0.1:8000/docs>

---

## Fluxo de uso sugerido

1. Abra a interface em `http://127.0.0.1:8000/`.
2. Confira se o binário local do Tor foi detectado.
3. Ajuste `SOCKSPort`, `ControlPort`, `DataDirectory` e `Log` (se necessário).
4. Clique em **Salvar torrc**.
5. Crie um Onion Service informando:
   - nome da pasta
   - porta pública (ex.: `80`)
   - host interno (ex.: `127.0.0.1`)
   - porta interna da app (ex.: `3000`)
6. Clique em **Criar onion**.
7. Clique em **Iniciar** ou **Reiniciar Tor**.
8. Leia o endereço `.onion` no arquivo `hostname` da pasta criada.

---

## Exemplo prático

Se sua aplicação local está em `127.0.0.1:3000`, configure:

- Nome da pasta: `meu-site`
- Porta pública: `80`
- Host interno: `127.0.0.1`
- Porta interna: `3000`

Isso gera algo equivalente a:

```torrc
HiddenServiceDir .../backend/vendor/tor/state/onions/meu-site
HiddenServicePort 80 127.0.0.1:3000
```

Depois que o Tor subir, o endereço `.onion` aparecerá em:

```text
backend/vendor/tor/state/onions/meu-site/hostname
```

---

## Desenvolvimento da UI (opcional)

Se quiser iterar no frontend separadamente:

```bash
cd frontend
npm install
npm run dev
```

Para build de produção da UI:

```bash
npm run build
```

Quando `frontend/dist` existe, o backend passa a servir a interface buildada automaticamente.

---

## Testes do backend

```bash
cd backend
source .venv/bin/activate  # no Windows, use .\.venv\Scripts\Activate.ps1
pytest
```

---

## Rodando com Docker Compose (desenvolvimento)

```bash
docker compose -f docker/docker-compose.yml up --build
```

API disponível em `http://127.0.0.1:8000`.

---

## Troubleshooting rápido

- **Servidor "cai" ao iniciar o Tor em modo `--reload`**:
  - Isso normalmente não é crash do FastAPI: o *reloader* detecta alterações em `backend/vendor/tor/state` (logs/data do Tor) e reinicia o processo.
  - Rode sem reload (`uvicorn app.main:app`) ou use `--reload-exclude "vendor/tor/state/*"` e `--reload-exclude "tunator.db"`.
- **Tor não inicia**: rode novamente o bootstrap (`bootstrap_backend.ps1` / `bootstrap_backend.sh`).
- **Porta em uso**: ajuste `SOCKSPort`/`ControlPort` no `torrc` pela interface.
- **`.onion` não aparece**: confira permissões de escrita em `backend/vendor/tor/state/onions`.
- **UI não carrega**: verifique se o backend está em execução e sem erro no terminal.
