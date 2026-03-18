# Python Backend

Tato slozka je novy cilovy backend pro FotoNabidku.

Smer:

- FastAPI
- SQLAlchemy 2.x
- Alembic
- Pydantic v2
- PostgreSQL
- Redis
- Python AI integrace

Aktualne je pripraveny zaklad vedle puvodniho Node prototypu:

- FastAPI app bootstrap
- settings pres pydantic-settings
- zakladni logging pres structlog
- API router a health endpoint
- SQLAlchemy Base, async session a prvni domenove modely
- modul `projects`
- modul `photos` vcetne local uploadu, primary photo a derivative metadata
- modul `analysis` vcetne mock AI provideru a manualni korekce plochy
- modul `quote-variants` vcetne recalculate logiky a quote items
- kanonicky API kabat `cases / images / analysis-jobs / measurements / estimates / pricebooks`

Zamer:

- nebourat fungujici frontendovy prototyp
- postupne prevadet backend moduly
- sjednotit dalsi rust do Python stacku
- drzet stare route jen jako kompatibilni most, nove veci smerovat do kanonicke domeny

Nejblizsi dalsi krok:

- pripravit databazove migrace
- dodelat material-catalog a suppliers jako samostatne sluzby
- potom prepojit React kancelar na Python API
