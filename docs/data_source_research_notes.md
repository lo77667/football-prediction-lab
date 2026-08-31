
## Discovered candidate

3. `https://github.com/dspinellis/awesome-rest-apis` — its Sports section currently lists a World Cup 2026 Tour API.
4. `https://ay-worldcup2026.zeabur.app/api/public/v1/matches?timezone=UTC` — endpoint responded successfully with JSON containing `version`, `count: 104`, timezone, and match records. Records include match ID, stage/group, venue, kickoff timestamps, home/away codes and names, attribution links, and share assets. This is real HTTP data for fixtures, but it is a fixture/schedule source, not historical results, odds, injuries, or event streams. It is therefore suitable for a fixture-source adapter and point-in-time schedule tests, not for claiming model accuracy.

The source includes attribution snippets in the response. Any integration must preserve attribution and verify the provider's terms before production use.

5. `https://github.com/whizkydee/Awesome-APIs` — general REST API design/resource list, not a verified football data provider. The repository is behind its upstream fork and its visible content is primarily API design guidance.
6. `https://free-apis.github.io/` — an aggregator derived from Public APIs and Public APIs Dev. It provides browse/category pages but is not itself a football data endpoint; entries require individual validation.

7. `https://publicapis.dev/category/sports-and-fitness` — lists football-related candidates including API-FOOTBALL, Football, Football Highlights, Football Standings, Football-Data, iSports API, and a Soccer/Football API. It also lists Cloudbet, but that includes betting/order functionality and is excluded from the project scope. The catalog page itself is not sufficient evidence of free access or license; each candidate needs direct validation.

8. `https://publicapis.dev/resource/football-data/4gymhkjx` and the linked `https://www.football-data.org/` — Football-Data.org is described as a REST API with machine-readable live scores, fixtures, tables, squads, and lineups/subs. The catalog page states a free tier for top competitions and paid plans for additional competitions/in-depth data; historical data or custom requests may require direct contact. This is the strongest candidate from the supplied lists for a source adapter, subject to checking its current API token policy and license.

## Direct endpoint smoke tests

- `https://api.football-data.org/v4/competitions/PL/matches?status=FINISHED&limit=1` returned HTTP 403 without a provider token: `restricted ... not within your permissions`. It is not usable anonymously in the current environment, so no fake token or fabricated response was added.
- `https://ay-worldcup2026.zeabur.app/api/public/v1/matches?timezone=UTC` returned valid JSON with version `2026.06.19.23`, count `104`, and fixture fields. A real adapter was added with explicit network opt-in, validation, cache, rate interval, UTC normalization, response SHA-256, and attribution extraction.
