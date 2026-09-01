# Free Public APIs review

The site `https://www.freepublicapis.com/` presents itself as a collection of 659 free public APIs and says the APIs are tested daily. It provides filters for reliability, no errors, popular/new APIs, and categories including Sport, News, Public Data, and Weather. The site is an index/catalog, not automatically the owner of every listed API; each source must be opened and validated independently.

The homepage currently highlights a `Football Data API` with three endpoints and a displayed API-health score of 90. Its description says it covers football areas, competitions, teams, matches, standings, scorers, and players. This is a candidate for the project, but the catalog description alone does not establish the original provider's license, rate limit, data freshness, historical coverage, or whether authentication is required.

The site also exposes an API navigation item and source pages. The next validation step is to open `/football-data-api`, extract the original endpoint(s), and test them without inventing credentials. No source should enter the NQBE pipeline solely because the catalog labels it free or reliable.

## Validation findings

The catalog page lists a legitimate documentation link for `https://www.football-data.org/documentation/quickstart` and the official endpoint `https://api.football-data.org/v4/competitions/`. It also displays an unrelated suspicious endpoint containing a token-like string in a URL and a hockey Flashscore path. That entry is untrusted catalog content and must not be used or copied into the project. The official Football-Data.org client already exists in the repository and requires `FOOTBALL_DATA_API_TOKEN` via the `X-Auth-Token` header.

FreePublicAPIs also publishes its own catalog API at `https://www.freepublicapis.com/api`, documented as limited to 1000 requests per day. Its listed endpoints include `/api/random`, `/api/apis/{id}`, and `/api/apis?sort=best&limit=20`. This catalog API is useful for source discovery or a periodic health report, but it should not be part of the prediction data path and its entries must be validated independently.
