# finally

# Um painel desenvolvido em Python, focado em consultas a fontes públicas de dados, validações locais e automação de buscas.

---

## Funções do painel

O painel está estruturado em módulos independentes acessíveis via terminal interativo:

1. **Módulo Avançado de Inteligência de CPF**:
   - **Consulta Direta Completa**: Varredura integrada em bases públicas (Portal da Transparência) e cadastros federais.
   - **Força Bruta Otimizada por Máscara**: Geração matemática instantânea e validação de combinações a partir de coringas (ex: `XXX.861.821-XX`).
2. **Consulta CEP**: Integração direta com a API do ViaCEP para localização geográfica e de logradouros.
3. **Consulta IP & Geolocalização**: Análise detalhada de endereços IP (versão, escopo público/privado e dados geográficos via `ipwho.is`).
4. **DNS & Resolução de Domínio**: Extração de registros e endereços associados a alvos de rede.
5. **WHOIS / RDAP**: Consulta de registros de domínio e informações de propriedade técnica.
6. **Enumeração de Subdomínios**: Mapeamento de subdomínios utilizando certificados públicos (`crt.sh`).
7. **Consulta CNPJ**: Consulta de dados cadastrais de pessoas jurídicas (Brasil API).
8. **User Checker**: Verificação simultânea de disponibilidade de nomes de usuário em redes e plataformas globais (GitHub, GitLab, Instagram, TikTok, YouTube, Reddit).
