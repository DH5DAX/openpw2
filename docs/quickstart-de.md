# openpw2 – Kurzstart

Eigenständige Python-App zur LAN-Steuerung des IC-PW2. Kein HamRig-Gateway und
keine installierte RS-PW2-App nötig. MIT-Lizenz; unabhängiges Projekt.

## Starten

Im portablen Windows-Paket `openpw2.exe` starten. Den Ordner `_internal`
daneben lassen. Die App installiert keinen Dienst und startet getrennt.
Alternativ aus dem Quellcode:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[gui]"
.venv\Scripts\python -m openpw2
```

**Try demo** öffnet eine lokale Simulation. **Operate → Simulate TX** zeigt
bewegte Messwerte ohne Netzwerkverbindung oder Funkbetrieb.

Unter **Connection** Adresse, Benutzer-ID, Passwort und Netzspannung eintragen.
Standardport: 50200. Andere PW2-LAN-Clients vorher trennen, insbesondere RS-PW2
oder den PW2-Treiber im HamRig-Gateway. Die App beendet diese nicht selbst.
Das Passwort wird nicht gespeichert. Die Netzspannungsangabe ist eine
Bedienereinstellung, keine Messung; unbekannte/niedrige Spannung sperrt 1 kW.

**Monitor & control** zeigt Leistung, SWR, Id, Vd, ALC, PA-Temperaturbalken,
Ansauglufttemperatur/Feuchte und alle bereits zugeordneten Bedienelemente.
Ein langer Druck auf die Meteranzeige am PW2 schaltet auf Balkenansicht; erst
diese liefert alle sechs Instrumente. **Reference** zeigt den dekodierten
Status als JSON und bietet einen Export ohne Zugangsdaten.

`≈` bedeutet aus der Anzeigeskala geschätzt. SWR wird nur zwischen 1,1 und 3,0
numerisch geschätzt. Die 28-°C-Anzeige ist Ansaugluft, nicht PA-Temperatur.
Graue Tasten zeigen beim Darüberfahren den Sperrgrund. Start tune bestätigt
den Start des Vorgangs; ein erfolgreicher Match wird damit nicht behauptet.

Die direkte Hardware-Abnahme dieser neuen App steht noch aus. Alle bisherigen
Erkenntnisse, Testbelege und offenen Funktionen stehen in [status.md](status.md).
