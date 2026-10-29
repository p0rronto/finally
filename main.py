import ipaddress
import json
import os
import re
import shutil
import socket
import time
import urllib.parse
import itertools

try:
    import sqlite3
except ImportError:
    sqlite3 = None

import requests

TIMEOUT = 6
HEADERS = {"User-Agent": "TerminalOSINT/3.0 (Professional Edition)"}

# Cores ANSI (Textos em BRANCO e destaques profissionais)
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
WHITE = "\033[97m"
GRAY = "\033[90m"
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"


def init_db():
    """Inicializa o banco de dados local SQLite"""
    if sqlite3 is None:
        return
    conn = sqlite3.connect("base_dados.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chave_tipo TEXT,
            chave_valor TEXT UNIQUE,
            nome TEXT,
            documento TEXT,
            banco TEXT,
            detalhes TEXT
        )
    """)
    conn.commit()
    conn.close()


def enable_windows_ansi():
    if os.name == "nt":
        try:
            os.system("")
        except Exception:
            pass


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def terminal_width():
    return max(60, min(shutil.get_terminal_size((80, 24)).columns, 100))


def line(char="─", color=GRAY):
    print(f"{color}{char * terminal_width()}{RESET}")


def title(text):
    width = min(terminal_width(), 76)
    print()
    print(f"{WHITE}{'═' * width}{RESET}")
    print(f"{BOLD}{WHITE}{text.center(width)}{RESET}")
    print(f"{WHITE}{'═' * width}{RESET}")


def banner():
    clear_screen()
    print(f"{WHITE}{BOLD}")
    print("██████╗ ██╗   ██╗    ██████╗  ██████╗ ██████╗ ██████╗  ██████╗ ███╗   ██╗████████╗ ██████╗ ")
    print("██╔══██╗╚██╗ ██╔╝    ██╔══██╗██╔═████╗██╔══██╗██╔══██╗██╔═══██╗████╗  ██║╚══██╔══╝██╔═══██╗")
    print("██████╔╝ ╚████╔╝     ██████╔╝██║██╔██║██████╔╝██████╔╝██║   ██║██╔██╗ ██║   ██║   ██║   ██║")
    print("██╔══██╗  ╚██╔╝      ██╔═══╝ ████╔╝██║██╔══██╗██╔══██╗██║   ██║██║╚██╗██║   ██║   ██║   ██║")
    print("██████╔╝   ██║       ██║     ╚██████╔╝██║  ██║██║  ██║╚██████╔╝██║ ╚████║   ██║   ╚██████╔╝")
    print("╚═════╝    ╚═╝       ╚═╝      ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ")
    print(f"{RESET}")
    line("━", WHITE)
    print()


def get(url, **kwargs):
    kwargs.setdefault("headers", HEADERS)
    kwargs.setdefault("timeout", TIMEOUT)
    return requests.get(url, **kwargs)


def clean_digits(value):
    return re.sub(r"\D", "", value)


def _calc_digit(partial: str, weight: int) -> int:
    soma = sum(int(d) * w for d, w in zip(partial, range(weight, 1, -1)))
    resto = (soma * 10) % 11
    return 0 if resto >= 10 else resto


def _build_cpf(base9: str) -> str | None:
    if len(set(base9)) == 1:
        return None
    d1 = _calc_digit(base9, 10)
    d2 = _calc_digit(base9 + str(d1), 11)
    return base9 + str(d1) + str(d2)


def fmt_cpf(cpf: str) -> str:
    clean = clean_digits(cpf)
    if len(clean) != 11:
        return cpf
    return f"{clean[:3]}.{clean[3:6]}.{clean[6:9]}-{clean[9:]}"


def cpf_valid(value):
    cpf = clean_digits(value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    nums = [int(digit) for digit in cpf]
    first = (sum(nums[i] * (10 - i) for i in range(9)) * 10) % 11
    first = 0 if first == 10 else first
    if first != nums[9]:
        return False
    second = (sum(nums[i] * (11 - i) for i in range(10)) * 10) % 11
    second = 0 if second == 10 else second
    return second == nums[10]


def pause():
    input(f"\n{GRAY}Pressione ENTER para retornar ao menu principal...{RESET}")


def query_transparencia(cpf_str):
    search_url = "https://busca.portaldatransparencia.gov.br/busca/pessoa-fisica"
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": "https://portaldatransparencia.gov.br/pessoa-fisica/busca/lista",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        resp = requests.get(
            search_url,
            params={"termo": cpf_str, "pagina": 1, "tamanhoPagina": 5, "t": "wtwLC1ItJOLhvc2n6rhY"},
            headers=headers,
            timeout=3
        )
        if resp.status_code == 200:
            data = resp.json()
            records = data.get("registros", [])
            out = []
            for rec in records:
                name = rec.get("nome", "").title()
                raw_cpf = rec.get("cpf", "")
                formatted = fmt_cpf(raw_cpf) if raw_cpf else fmt_cpf(cpf_str)
                out.append({"cpf": formatted, "nome": name, "fonte": "Portal da Transparência"})
            return out
    except Exception:
        pass
    return []


def query_sus_cadastros(cpf_str):
    """Consulta avançada integrada em bases públicas e cadastrais de saúde/SUS"""
    try:
        # Endpoint de consulta pública adaptado de cadastros federais
        url = f"https://cartao.sus.gov.br/portal/rest/v1/cidadao/consultar"
        headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
        # Realiza validação ou busca cruzada por CPF
        resp = requests.post(url, json={"documento": cpf_str}, headers=headers, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if data and "nome" in data:
                return {
                    "cpf": fmt_cpf(cpf_str),
                    "nome": data.get("nome", "").title(),
                    "mae": data.get("nomeMae", "Não informado").title(),
                    "nascimento": data.get("dataNascimento", "N/A"),
                    "fonte": "Base Nacional Cadastral / SUS"
                }
    except Exception:
        pass
    return None


def cpf_menu():
    title("MÓDULO AVANÇADO DE INTELIGÊNCIA DE CPF")
    print(f"  {WHITE}[1]{RESET} Consulta Direta Completa (Transparência + Cadastros SUS)")
    print(f"  {WHITE}[2]{RESET} Força Bruta Otimizada por Máscara (Ex: XXX.861.821-XX)")
    print(f"  {RED}[0]{RESET} Voltar")
    
    choice = input(f"\n{CYAN}Opção » Opção: {RESET}").strip()
    if choice == "0":
        return

    if choice == "1":
        cpf_input = input("Digite o CPF (ex: 12345678909): ").strip()
        digits = clean_digits(cpf_input)
        if len(digits) != 11:
            print(f"{RED}[!] O CPF precisa conter exatamente 11 dígitos.{RESET}")
            return
        
        formatted = fmt_cpf(digits)
        valid = cpf_valid(digits)
        
        print(f"\n{WHITE}CPF Informado : {formatted}{RESET}")
        print(f"{WHITE}Dígito Matem. : {'VÁLIDO' if valid else 'INVÁLIDO'}{RESET}")
        
        print(f"\n{CYAN}[⚡] Consultando bases governamentais e cadastrais...{RESET}")
        
        # Busca na Transparência
        results = query_transparencia(digits)
        
        # Busca complementar em cadastros federais / SUS
        sus_data = query_sus_cadastros(digits)
        
        print("-" * 60)
        found = False
        if results:
            found = True
            print(f"{GREEN}[+] Registros na Transparência ({len(results)}):{RESET}\n")
            for r in results:
                print(f"    • Nome Completo : {WHITE}{r['nome']}{RESET}")
                print(f"    • CPF Formatado : {WHITE}{r['cpf']}{RESET}")
                print(f"    • Fonte         : {GRAY}{r['fonte']}{RESET}")
                print("-" * 60)
                
        if sus_data:
            found = True
            print(f"{GREEN}[+] Informações Complementares Cadastrais:{RESET}\n")
            print(f"    • Nome Completo : {WHITE}{sus_data['nome']}{RESET}")
            print(f"    • Nome da Mãe   : {WHITE}{sus_data['mae']}{RESET}")
            print(f"    • Nascimento    : {WHITE}{sus_data['nascimento']}{RESET}")
            print(f"    • Fonte         : {GRAY}{sus_data['fonte']}{RESET}")
            print("-" * 60)
            
        if not found:
            print(f"{YELLOW}[-] Nenhum registro público detalhado encontrado para este CPF.{RESET}")
            print("-" * 60)

    elif choice == "2":
        mask_input = input("Digite a máscara (Ex: XXX.456.789-XX ou ***456789**): ").strip().upper()
        mask_normalized = mask_input.replace("*", "X")
        
        clean_mask = re.sub(r"[^0-9Xx]", "", mask_normalized)
        if len(clean_mask) != 11:
            print(f"{RED}[!] A máscara formatada precisa ter exatamente 11 caracteres.{RESET}")
            return

        print(f"\n{CYAN}[⚡] Gerando combinações e varrendo com alta velocidade...{RESET}")
        prefix = list(clean_mask[:9])
        x_pos = [i for i, c in enumerate(prefix) if c == "X"]
        
        candidates = []
        for combo in itertools.product(range(10), repeat=len(x_pos)):
            base = prefix.copy()
            for pos, digit in zip(x_pos, combo):
                base[pos] = str(digit)
            cpf_cand = _build_cpf("".join(base))
            if cpf_cand:
                candidates.append(cpf_cand)

        print(f"{GRAY}[i] Total de CPFs válidos a testar: {len(candidates)}{RESET}")
        
        found_results = []
        for idx, c in enumerate(candidates, 1):
            print(f"\r{GRAY}[»] Testando candidato {idx}/{len(candidates)}...{RESET}", end="", flush=True)
            res = query_transparencia(c)
            if res:
                for r in res:
                    if r not in found_results:
                        found_results.append(r)
            time.sleep(0.08)

        print("\r" + " "*50 + "\r", end="")
        print("-" * 60)
        if found_results:
            print(f"{GREEN}[+] Sucesso! Registros encontrados ({len(found_results)}):{RESET}\n")
            for r in found_results:
                print(f"    • Nome Completo : {WHITE}{r['nome']}{RESET}")
                print(f"    • CPF Formatado : {WHITE}{r['cpf']}{RESET}")
                print("-" * 60)
        else:
            print(f"{YELLOW}[-] Nenhum registro encontrado para as combinações desta máscara.{RESET}")
            print("-" * 60)


def cep_lookup():
    title("CONSULTA CEP")
    cep = clean_digits(input("Digite o CEP (8 dígitos): "))
    if len(cep) != 8:
        print(f"{RED}[!] CEP inválido. Deve conter 8 dígitos.{RESET}")
        return
    try:
        response = get(f"https://viacep.com.br/ws/{cep}/json/")
        response.raise_for_status()
        data = response.json()
        if data.get("erro"):
            print(f"{RED}[!] CEP não encontrado na base de dados.{RESET}")
            return
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except (requests.RequestException, ValueError) as exc:
        print(f"{RED}[!] Erro na consulta: {exc}{RESET}")


def ip_lookup():
    title("CONSULTA IP & GEOLOCALIZAÇÃO")
    value = input("Digite o endereço IP: ").strip()
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        print(f"{RED}[!] Endereço IP inválido.{RESET}")
        return
    
    result = {
        "ip": str(ip),
        "versao": ip.version,
        "privado": ip.is_private,
        "global": ip.is_global,
    }
    try:
        response = get(f"https://ipwho.is/{urllib.parse.quote(value, safe='')}")
        response.raise_for_status()
        data = response.json()
        if data.get("success", True):
            for key in ("type", "continent", "country", "region", "city", "latitude", "longitude", "connection"):
                if key in data:
                    result[key] = data[key]
        else:
            result["aviso"] = f"Geolocalização indisponível: {data.get('message', 'sem detalhes')}"
    except (requests.RequestException, ValueError) as exc:
        result["aviso"] = f"Consulta externa indisponível: {exc}"
        
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


def normalize_domain(value):
    value = value.strip()
    if "://" in value:
        value = urllib.parse.urlparse(value).hostname or ""
    return value.rstrip(".").lower()


def dns_lookup():
    title("DNS & RESOLUÇÃO DE DOMÍNIO")
    domain = normalize_domain(input("Domínio (ex: example.com): "))
    if not domain or "/" in domain or " " in domain:
        print(f"{RED}[!] Domínio inválido.{RESET}")
        return
    
    result = {"dominio": domain, "ip": [], "registros": {}}
    try:
        result["ip"] = sorted({item[4][0] for item in socket.getaddrinfo(domain, None, type=socket.SOCK_STREAM)})
    except socket.gaierror as exc:
        result["erro_ip"] = str(exc)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def whois_rdap():
    title("WHOIS / RDAP (REGISTRO DE DOMÍNIO)")
    domain = normalize_domain(input("Domínio: "))
    if not domain or "/" in domain or " " in domain:
        print(f"{RED}[!] Domínio inválido.{RESET}")
        return
        
    url = "https://rdap.org/domain/" + urllib.parse.quote(domain, safe=".-")
    try:
        response = get(url)
        print(f"Status HTTP: {response.status_code}")
        if response.ok:
            data = response.json()
            print(json.dumps(data, indent=2, ensure_ascii=False)[:15000])
        else:
            print(f"{YELLOW}[!] Consulta RDAP indisponível para esse domínio.{RESET}")
    except (requests.RequestException, ValueError) as exc:
        print(f"{RED}[!] Erro: {exc}{RESET}")


def subdomains():
    title("ENUMERAÇÃO DE SUBDOMÍNIOS (CRT.SH)")
    domain = normalize_domain(input("Domínio alvo: "))
    if not domain or "." not in domain or "/" in domain or " " in domain:
        print(f"{RED}[!] Domínio inválido.{RESET}")
        return
        
    try:
        response = get("https://crt.sh/", params={"q": f"%.{domain}", "output": "json"})
        response.raise_for_status()
        entries = response.json()
        found = set()
        for entry in entries:
            for name in entry.get("name_value", "").splitlines():
                name = name.strip().lower().lstrip("*.")
                if name == domain or name.endswith("." + domain):
                    found.add(name)
        result = sorted(found)
        print(f"\n{GREEN}[+] Subdomínios encontrados: {len(result)}{RESET}")
        print("\n".join(result[:300]) or "Nenhum resultado.")
    except (requests.RequestException, ValueError) as exc:
        print(f"{RED}[!] Erro na consulta: {exc}{RESET}")


def cnpj_lookup():
    title("CONSULTA CNPJ (BRASIL API)")
    cnpj = clean_digits(input("CNPJ (14 dígitos): "))
    if len(cnpj) != 14:
        print(f"{RED}[!] CNPJ inválido. Deve conter 14 dígitos.{RESET}")
        return
        
    try:
        response = get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}")
        if response.status_code != 200:
            print(f"{YELLOW}[!] CNPJ não encontrado ou serviço indisponível (HTTP {response.status_code}).{RESET}")
            return
        data = response.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except (requests.RequestException, ValueError) as exc:
        print(f"{RED}[!] Erro: {exc}{RESET}")


def user_checker():
    title("VERIFICADOR DE PERFIS PÚBLICOS")
    username = input("Nome de usuário alvo: ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", username):
        print(f"{RED}[!] Nome de usuário inválido.{RESET}")
        return
        
    sites = {
        "GitHub": f"https://github.com/{username}",
        "GitLab": f"https://gitlab.com/{username}",
        "Reddit": f"https://www.reddit.com/user/{username}/",
        "YouTube": f"https://www.youtube.com/@{username}",
        "TikTok": f"https://www.tiktok.com/@{username}",
        "Instagram": f"https://www.instagram.com/{username}/",
    }
    results = {}
    for site, url in sites.items():
        try:
            response = get(url, allow_redirects=True)
            results[site] = {
                "url": url,
                "status_http": response.status_code,
                "resultado": "Possível perfil ativo" if response.status_code == 200 else "Não encontrado ou protegido",
            }
        except requests.RequestException as exc:
            results[site] = {"url": url, "resultado": f"Erro na consulta: {exc}"}
            
    print(json.dumps(results, indent=2, ensure_ascii=False))


def main():
    enable_windows_ansi()
    init_db()
    options = {
        "1": ("Módulo Avançado de Inteligência de CPF", cpf_menu),
        "2": ("Consulta CEP (ViaCEP)", cep_lookup),
        "3": ("Consulta IP & Geolocalização", ip_lookup),
        "4": ("DNS / Registros de Domínio", dns_lookup),
        "5": ("WHOIS / RDAP", whois_rdap),
        "6": ("Enumeração de Subdomínios", subdomains),
        "7": ("Consulta CNPJ", cnpj_lookup),
        "8": ("User Checker (Perfis Globais)", user_checker),
    }
    while True:
        banner()
        print(f"  {WHITE}{BOLD}MÓDULOS DE OPERAÇÃO DISPONÍVEIS{RESET}\n")
        for number, (name, _) in options.items():
            print(f"  {WHITE}[{number:>2}]{RESET}  {WHITE}{name}{RESET}")
        print(f"\n  {RED}[ 0]{RESET}  Encerrar Painel")
        line("─", WHITE)
        choice = input(f"\n  {CYAN}Decida a opção{RESET} {WHITE}»{RESET} ").strip()
        if choice == "0":
            print(f"\n{RED}[*] Encerrando o painel com segurança...{RESET}")
            break
        if choice not in options:
            print(f"\n{RED}[!] Opção inválida.{RESET}")
            time.sleep(1)
            continue
            
        clear_screen()
        try:
            options[choice][1]()
        except KeyboardInterrupt:
            print(f"\n{YELLOW}[!] Operação cancelada pelo usuário.{RESET}")
        except Exception as exc:
            print(f"\n{RED}[ERRO CRÍTICO] {exc}{RESET}")
        pause()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{RED}Painel encerrado pelo operador.{RESET}")
