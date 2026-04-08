# Runtime local do Tor

O Tunator agora opera com um **Tor local do projeto**.

## Princípios

- não depender do serviço do sistema operacional
- não depender de caminhos globais do SO
- manter `torrc`, logs e dados dentro do projeto
- facilitar empacotamento futuro

## Fluxo

1. identificar a plataforma atual
2. localizar bundle já presente em `backend/vendor/tor/archives/`
3. se não existir e o bootstrap permitir, baixar o bundle oficial
4. extrair o conteúdo para `backend/vendor/tor/runtime/<plataforma>`
5. gerar `backend/vendor/tor/state/torrc`
6. iniciar o processo do Tor usando o binário local

## Limitações atuais

- o app ainda não verifica assinatura `.asc` automaticamente
- o controle continua sendo de processo local, não de serviço persistente
- o frontend ainda não expõe o fluxo completo de bootstrap
