# Security Notes

- API focada em uso local.
- `torrc` é escrito com estratégia atômica (tmp + fsync + rename).
- Backups são listáveis e restauráveis.
- Extração de bundle valida path traversal.
- Integração com ControlPort usa cookie auth quando disponível via Stem.
