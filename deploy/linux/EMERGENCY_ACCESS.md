# Nouzový přístup (break-glass) – Private Core

Běžná správa probíhá výhradně přes administrační WireGuard tunel `wg-nc-admin` (`ssh admin@10.51.0.1`). SSH na veřejném rozhraní je zavřené (nftables + Hetzner Cloud Firewall).

Tento postup platí, když administrační tunel nefunguje: výpadek WireGuardu, ztracený klíč, chyba v nftables.

## Předpoklady (připravit předem)
1. **Lokální break-glass účet** `nc-breakglass` s heslem, které funguje **jen na konzoli** (tty). SSH pro něj zakazuje `DenyUsers nc-breakglass` v `sshd_config`. Heslo je offline v trezoru a mají ho dva lidé.
2. **Druhý administrační peer** (záložní zařízení) v `wg-nc-admin`, uložený offline.
3. Přístup do Hetzner Cloud Console je chráněný MFA a mají ho jen správci.

## Postup
1. **Ověřit, jestli stačí záložní peer.** Pokud funguje, opravit tunel přes něj a skončit.
2. **Hetzner Cloud Console → server → Console (VNC).** Přihlásit se jako `nc-breakglass` a přes `sudo` opravit WireGuard nebo nftables:
   ```sh
   systemctl status wg-quick@wg-nc-admin
   journalctl -u wg-quick@wg-nc-admin -n 50
   nft list ruleset | less
   ```
3. **Když je potřeba SSH zvenku** (např. přenos souborů), povolit ho dočasně jen pro jednu veřejnou adresu:
   ```sh
   nft add element inet nc ssh_emergency { <tvoje-veřejná-IPv4> timeout 1h }
   ```
   Pak v Hetzner Cloud Firewall přidat dočasné pravidlo `TCP 22` z `<IP>/32` a po práci ho odebrat. Položka v nftables po hodině sama vyprší.
4. **Když nejde ani konzole:** Hetzner Rescue System → připojit disk → opravit `/etc/nftables.conf` nebo `/etc/wireguard/*` → restart.
5. **Po zásahu:**
   - zkontrolovat, že `ssh_emergency` je prázdná (`nft list set inet nc ssh_emergency`),
   - odebrat pravidlo z Hetzner Firewallu,
   - zapsat zásah do provozního deníku (kdo, kdy, proč, co se měnilo),
   - spustit `deploy/linux/tests/network_isolation.sh` (`VANTAGE=internet`).

## Co nikdy
- Neotevírat SSH trvale na veřejném rozhraní a nepovolovat přihlášení heslem přes SSH.
- Nepřidávat do `ssh_emergency` rozsahy (CIDR), jen jednotlivé adresy s timeoutem.
- Nevypínat nftables (`nft flush ruleset`) na serveru s veřejnou IP. Při ladění použít `nft -c -f`.
