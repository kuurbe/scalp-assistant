# KrowdGuide - Data Sources & API Research
## Comprehensive Research Document (March 2026)

---

# 1. REAL-TIME CROWD / FOOT TRAFFIC DATA

## BestTime.app
- **Data:** Hourly foot traffic forecasts (0-100% relative busyness) for public venues across 150+ countries. Live busyness comparison against historical averages. Surge analysis for arrival/departure patterns.
- **API Format:** REST API. Endpoints include venue search by query, venue forecast by name/ID, live busyness data. Natural language search supported ("Brunch places in Paris").
- **Free Tier:** Free test account with limited credits for evaluation.
- **Pricing:** Usage-based starting at $29/mo ($0.04-0.06/credit). Fixed plan at $99/mo ($0.001-0.009/credit depending on volume). Credits vary by endpoint: 1-5 credits per call.
- **Data Freshness:** Forecasts are historical weekly patterns; live data is real-time where available.
- **Relevance:** HIGH - Direct fit for "how busy is this place right now" feature. Covers restaurants, bars, gyms, museums, retail.
- **Status:** Active, well-documented.
- **Links:** https://besttime.app, https://documentation.besttime.app

## SafeGraph / Advan Research (via Dewey)
- **Data:** Aggregated anonymized foot traffic counts for POIs and census block groups. Demographics, area of origin, dwell patterns. Derived from mobile device location signals (~35M phones in US panel).
- **API Format:** Data delivery via Dewey marketplace. Bulk datasets, not real-time API calls. US and Canada coverage.
- **Free Tier:** Academic access available via Dewey. No free commercial tier.
- **Pricing:** Enterprise/custom. Contact sales.
- **Data Freshness:** Weekly or monthly aggregated datasets. Not real-time.
- **Relevance:** MEDIUM - Better for analytics/planning than real-time consumer features. Good for understanding neighborhood traffic patterns.
- **Status:** Active. SafeGraph provides POI/geometry data; Advan provides the mobility/foot traffic data (post-2023 transition).
- **Links:** https://www.deweydata.io/data-partners/advan

## Placer.ai
- **Data:** Real-time foot traffic, visitor demographics, trade area analysis, competitive benchmarking, customer journey mapping, dwell time, cross-visitation, market share. Panel of tens of millions of devices with ML-based estimations.
- **API Format:** REST API for extracting data into third-party apps. Dashboard also available.
- **Free Tier:** Free POI tools on website. API requires paid subscription.
- **Pricing:** Not publicly listed. Enterprise pricing - contact sales. Reviews indicate it is expensive.
- **Data Freshness:** Near real-time for traffic; historical for analytics.
- **Relevance:** MEDIUM - Powerful but likely too expensive for a consumer app. Better suited for enterprise real estate/retail analytics.
- **Status:** Active, growing rapidly.
- **Links:** https://www.placer.ai/products/api

## Google Popular Times
- **Data:** Historical busyness patterns and live visit data for businesses shown on Google Maps.
- **API Format:** NO OFFICIAL API EXISTS. Google has never released a public endpoint despite years of developer requests (tracked on Google Issue Tracker #35827550).
- **Workarounds:** (1) Python `populartimes` library (github.com/m-wrzr/populartimes) - uses Places API + scraping, legally questionable. (2) Third-party scraping services like ScrapingBee. (3) BestTime.app as an alternative data source.
- **Pricing:** N/A (no official API). Scraping services charge per call.
- **Data Freshness:** Live data shown on Google Maps, but not programmatically accessible.
- **Relevance:** HIGH relevance if accessible, but no reliable legal method to access.
- **Status:** No official API. Unofficial methods risk TOS violations and breakage.

## Gravy Analytics / Unacast
- **Data:** Location intelligence from billions of daily mobile location signals across 600M+ monthly devices in 180+ countries. Foot traffic, demographics, consumer behavior profiles.
- **API Format:** Enterprise API or bulk data delivery. Integrations with AWS, LiveRamp, Oracle, etc.
- **Free Tier:** Free data samples available on request.
- **Pricing:** $1/API call to $40,000/year depending on product.
- **Data Freshness:** Real-time signals processed daily.
- **Relevance:** LOW for consumer app - enterprise-grade, expensive, regulatory concerns. FTC filed complaint in Dec 2024 for collecting location data without consent.
- **Status:** Active but under regulatory scrutiny. Merged with Unacast in 2023.
- **Links:** https://gravyanalytics.com

## Orange CAMARA Population Density API (NEW - 2024-2026)
- **Data:** Telecom-derived population density data. Used during 2024 Paris Olympics to monitor 100 venue entry points. AI-enhanced prediction of mobility patterns and crowd surges.
- **API Format:** REST API following CAMARA (telecom industry standard) specifications.
- **Pricing:** Not publicly available; enterprise/telecom partnership model.
- **Data Freshness:** Real-time.
- **Relevance:** HIGH for large-event crowd monitoring. Limited to regions with Orange telecom infrastructure.
- **Status:** Active, expanding post-Olympics.
- **Links:** https://developer.orange.com

## Ariadne (NEW)
- **Data:** Real-time people counting, occupancy, dwell time, and flow analytics using hybrid Time-of-Flight + signal sensing. Privacy-first (no stored video).
- **API Format:** Hardware + software platform.
- **Pricing:** Custom. Requires physical sensor installation.
- **Relevance:** LOW for a mobile app (hardware-dependent). Could be useful if partnering with venues.
- **Status:** Active.

---

# 2. TRANSIT & COMMUTE DATA

## GTFS / GTFS-Realtime Feeds
- **Data:** Standardized public transit schedules (GTFS Static) and real-time updates including trip delays, cancellations, vehicle positions, and service alerts (GTFS-RT). Protocol Buffer format.
- **API Format:** Direct feeds from transit agencies. Each agency publishes its own endpoint. Common format across 1000+ agencies worldwide.
- **Free Tier:** Most agency feeds are free with registration.
- **Rate Limits:** Vary by agency. Typically require API key registration.
- **Key Agencies:**
  - **MTA (NYC):** Real-time subway, bus, railroad. Custom GTFS-RT extensions. Requires API key.
  - **WMATA (DC):** Free developer access. New Better Bus GTFS data available June 2025.
  - **CTA (Chicago/Metra):** API migrated to new version Nov 2025; requires re-registration.
- **Data Freshness:** Real-time (seconds to minutes).
- **Relevance:** CRITICAL - Essential for any city guide transit feature.
- **Status:** Active, growing. Global standard.
- **Links:** https://developers.google.com/transit/gtfs-realtime, https://www.mta.info/developers, https://developer.wmata.com

## Citymapper API
- **Data:** Transit journey planning, real-time transit data, walk/cycle/scooter travel times. Supports 20+ vehicle types including bus, metro, rail, ferry, bike, escooter.
- **API Format:** REST API + iOS/Android SDKs.
- **Free Tier:** 5,000 monthly requests free across all products.
- **Pricing:** Usage-based beyond free tier. Each successful HTTP 200 response = 1 credit. Enterprise pricing available.
- **Rate Limits:** Based on plan tier.
- **Data Freshness:** Real-time.
- **Relevance:** HIGH - Multi-modal routing is exactly what a city guide needs.
- **Status:** Active, well-documented.
- **Links:** https://docs.external.citymapper.com/api/

## Transit App
- **Data:** Real-time transit arrival predictions. GTFS best practices guidance for agencies.
- **API Format:** URL scheme integration for deep-linking into Transit app. Not a full data API for third-party consumption.
- **Free Tier:** N/A (integration-focused, not data API).
- **Relevance:** LOW as a data source; useful for deep-linking to transit directions.
- **Status:** Active.
- **Links:** https://transitapp.com/developers

## OpenTripPlanner (OTP)
- **Data:** Open-source multi-modal journey planning engine. Supports GTFS, NeTEx, OpenStreetMap data. Walking, biking, driving, transit routing.
- **API Format:** GraphQL APIs (REST removed in 2025). Self-hosted. Uses Raptor algorithm for transit routing.
- **Free Tier:** Fully open source (LGPL license). Free to deploy.
- **Pricing:** Free (self-hosted). Hosting costs are yours.
- **Data Freshness:** Real-time when connected to GTFS-RT feeds.
- **Relevance:** HIGH - Free, powerful, customizable. Requires server infrastructure.
- **Status:** Active. OTP2 is a major rewrite with significant performance improvements. R package updated July 2025.
- **Links:** https://docs.opentripplanner.org, https://github.com/opentripplanner/OpenTripPlanner

## Moovit API
- **Data:** Multimodal trip planning, real-time transit data. Powers governments and brands including Microsoft, Uber, Lyft, Cubic.
- **API Format:** REST APIs designed for speed and scalability.
- **Free Tier:** Not publicly listed.
- **Pricing:** Enterprise/custom. Contact sales.
- **Data Freshness:** Real-time.
- **Relevance:** HIGH - Industry-leading transit data coverage, but likely expensive.
- **Status:** Active.
- **Links:** https://moovit.com/maas-solutions/transit-apis/

---

# 3. WEATHER INTEGRATION

## OpenWeatherMap
- **Data:** Current weather, 5-day/3-hour forecasts, weather alerts, weather maps. One Call API 3.0 adds minutely/hourly/daily forecasts + historical data.
- **API Format:** REST API returning JSON. Endpoints: `/data/2.5/weather`, `/data/3.0/onecall`.
- **Free Tier:** 1,000 calls/day, 60 calls/min. One Call 3.0: 1,000 calls/day free (requires credit card on file).
- **Pricing:** Professional plans with fixed monthly pricing. Pay-as-you-go for One Call 3.0 overages.
- **Rate Limits:** 60 calls/min (free). HTTP 429 on exceed.
- **Data Freshness:** Real-time current; forecasts updated regularly.
- **Relevance:** HIGH - Industry standard, well-documented, generous free tier.
- **Status:** Active. ODbL licensed, commercial use allowed with attribution.
- **Links:** https://openweathermap.org/api

## Tomorrow.io
- **Data:** 80+ data fields including weather, air quality, soil data. Minute-by-minute precipitation forecasts up to 3 hours ahead at 500m resolution. Hyper-local observations.
- **API Format:** REST API. Endpoints: `/weather/forecast`, `/weather/realtime`.
- **Free Tier:** 500 API calls/day. Access to core weather parameters. Minute forecasts included.
- **Pricing:** Paid plans based on API call volume with annual discounts. Contact sales for enterprise.
- **Rate Limits:** Daily, hourly, and per-second limits on free plan.
- **Data Freshness:** Real-time, updated every minute.
- **Relevance:** HIGH - Minute-by-minute precipitation is perfect for "should I walk there now?" features.
- **Status:** Active.
- **Links:** https://www.tomorrow.io/weather-api/, https://docs.tomorrow.io

## Visual Crossing
- **Data:** Current weather, 15-day forecasts, 50+ years of historical data, 15-minute interval forecasts. Sourced from ECMWF, NOAA, WMO, NASA, JMA.
- **API Format:** REST API returning JSON/CSV.
- **Free Tier:** 1,000 records/day. Includes commercial use (with attribution). Full forecast + historical access.
- **Pricing:** Pay-as-you-go at $0.0001/record beyond free tier. Professional and Corporate plans available.
- **Data Freshness:** Real-time current; forecasts updated regularly.
- **Relevance:** HIGH - Best free tier for historical weather analysis. Good for "what's the weather usually like here in March?"
- **Status:** Active.
- **Links:** https://www.visualcrossing.com/weather-api/

## WeatherAPI.com
- **Data:** Real-time weather, 14-day forecasts, historical data from Jan 2010, future weather (365 days). UV index, solar radiation, astronomy data.
- **API Format:** REST API, single endpoint design.
- **Free Tier:** Status unclear - reports of free plan being dropped. May be limited to ~50 calls/day.
- **Pricing:** Paid plans from $25/mo (10K calls) to $100/mo (675K calls) via RapidAPI.
- **Relevance:** MEDIUM - Good features but free tier uncertainty is a concern.
- **Status:** Active but free tier reliability questionable.
- **Links:** https://www.weatherapi.com

## National Weather Service (NWS) API
- **Data:** Official US government forecasts, alerts, observations. ~2.5km grid resolution. JSON-LD format.
- **API Format:** REST API. No API key required. Base URL: `https://api.weather.gov`. Start with `/points/{lat},{lon}` to get forecast URLs.
- **Free Tier:** Completely free. No registration, no API key, no fees.
- **Rate Limits:** Unpublished but generous. 1-second delay between requests recommended. User-Agent header required.
- **Data Freshness:** Real-time observations; forecasts updated by local Weather Forecast Offices.
- **Relevance:** HIGH - Best free option for US weather. Official government data.
- **Status:** Active, regularly updated. OpenAPI 3.0 spec available. Dec 2025: precipitation rounding changes.
- **Links:** https://api.weather.gov, https://www.weather.gov/documentation/services-web-api

## Open-Meteo (BONUS - Open Source)
- **Data:** Hourly forecasts, 16-day outlooks, 80 years of historical data. Multiple weather models (NOAA GFS, ECMWF IFS, DWD ICON). Also marine, air quality, geocoding, elevation.
- **API Format:** REST API, JSON responses. No API key required.
- **Free Tier:** 10,000 calls/day, 5,000/hour, 600/min for non-commercial use. CC-BY 4.0 license.
- **Pricing:** Subscription plans for commercial use or >10K calls/day.
- **Data Freshness:** Hourly model updates; sub-10ms response times.
- **Relevance:** HIGH - Excellent free option, great developer experience, privacy-focused.
- **Status:** Active, open source on GitHub. Servers in Europe + North America.
- **Links:** https://open-meteo.com, https://github.com/open-meteo/open-meteo

---

# 4. EVENTS & ACTIVITIES

## Ticketmaster Discovery API
- **Data:** 230K+ events across US, Canada, Mexico, UK, Ireland, Australia, NZ, Europe. Event details, venues, performers, images, pricing, dates, classifications.
- **API Format:** REST API v2. Base: `https://app.ticketmaster.com/discovery/v2/`. JSON responses.
- **Free Tier:** YES - Completely free. 5,000 calls/day, 5 req/sec default.
- **Rate Limits:** 5,000/day, 5/sec (upgradable on request). Discovery Feed available for partners (no call limits, hourly refresh).
- **Data Freshness:** Real-time event listings.
- **Relevance:** HIGH - Major ticketed events, concerts, sports, theater.
- **Status:** Active, well-maintained.
- **Links:** https://developer.ticketmaster.com

## Eventbrite API
- **Data:** Millions of organizer-created events. Event details, categories, venues, ticket info.
- **API Format:** REST API. OAuth 2.0 authentication.
- **Free Tier:** API access available with free account. Full API access requires Premium plan.
- **Pricing:** Platform fees: 3.7% + $1.79/ticket + 2.9% payment processing. Pro plans $15-$100/mo.
- **Data Freshness:** Real-time event listings.
- **Relevance:** HIGH - Strong for local community events, workshops, meetups that Ticketmaster doesn't cover.
- **Status:** Active.
- **Links:** https://www.eventbrite.com/platform/api

## PredictHQ
- **Data:** 20M+ verified events across 30K cities. Scheduled events (concerts, sports, holidays, conferences) + unscheduled (airport delays, disasters, severe weather, terror). Events ranked by predicted impact on demand.
- **API Format:** REST API. Rich filtering by category, location, impact rank.
- **Free Tier:** 14-day trial, then limited Free Plan.
- **Pricing:** Custom/contact sales. Tailored to usage and business needs.
- **Data Freshness:** Real-time event intelligence with demand forecasting.
- **Relevance:** HIGH - Unique "demand intelligence" layer beyond raw event listings. Predicts how events impact foot traffic.
- **Status:** Active. Used by Uber, Booking.com, Dominos.
- **Links:** https://www.predicthq.com, https://docs.predicthq.com

## Foursquare Places API v3
- **Data:** 100M+ POIs globally. Venue details, categories, ratings, tips, photos, hours, popularity. Rich taxonomy of venue categories.
- **API Format:** REST API v3. Endpoints: Place Search, Place Details, Autocomplete, Geotagging.
- **Free Tier:** $200/mo free credits (sandbox). 10,000 Pro calls/month free.
- **Pricing:** Pro endpoints: ~$15/1,000 calls. Premium endpoints (photos, tips, hours): ~$18.75/1,000 calls. Volume discounts available.
- **Rate Limits:** Based on plan.
- **Data Freshness:** POI data updated regularly; tips/photos are user-generated.
- **Relevance:** HIGH - Rich venue data with categories, tips, and photos. Strong for discovery features.
- **Status:** Active. V2 endpoints being deprecated; pricing restructured June 2025.
- **Links:** https://foursquare.com/products/places-api/, https://foursquare.com/pricing/

## Google Places API (New)
- **Data:** Comprehensive global POI data. Place details, photos, reviews, opening hours, price levels, types, atmosphere. Address validation, geocoding.
- **API Format:** REST API with FieldMask-based pricing. Endpoints: Place Details (New), Nearby Search (New), Text Search (New), Autocomplete (New).
- **Free Tier:** 10,000 free calls/month per SKU (Essentials tier). Changed March 1, 2025 - replaced old $200/mo credit.
- **Pricing:** $2-$30 per 1,000 requests depending on SKU tier (Essentials/Pro/Enterprise) and fields requested. Volume discounts at 5M+ monthly events.
- **Data Freshness:** Real-time.
- **Relevance:** HIGH - Most comprehensive global POI database. Expensive at scale.
- **Status:** Active. Major pricing restructure March 2025. Legacy APIs being deprecated.
- **Links:** https://developers.google.com/maps/documentation/places

## SeatGeek API
- **Data:** Live events in America - concerts, sports, theater. Venue details (lat/lon), performer info, average ticket prices, seat maps.
- **API Format:** REST API returning JSON.
- **Free Tier:** Free API key with up to 500 events, sub-second response times.
- **Pricing:** Pay-per-use model based on verification volume.
- **Data Freshness:** Real-time event and pricing data.
- **Relevance:** MEDIUM-HIGH - Good complement to Ticketmaster for sports/concerts. Partner program earns $11/sale.
- **Status:** Active.
- **Links:** https://seatgeek.com/build, https://developer.seatgeek.com

---

# 5. FOOD & DINING

## Yelp Fusion API (Places API)
- **Data:** Millions of businesses. Restaurant details, ratings (1-5 stars), review counts, hours, photos, price range, categories, transactions (delivery, pickup, reservations).
- **API Format:** REST API. Endpoints: Business Search, Business Details, Reviews, Autocomplete.
- **Free Tier:** NO permanent free tier. 30-day trial with 5,000 calls.
- **Pricing:** Starter $7.99/1K calls (basic data), Plus $9.99/1K calls (includes reviews), Enterprise $14.99/1K calls. 30K calls/mo default, 5K/day limit.
- **Rate Limits:** 300 calls/day on trial. 5,000/day on paid plans.
- **Data Freshness:** Business data updated regularly; reviews real-time.
- **Relevance:** HIGH - Gold standard for restaurant discovery in the US. Expensive without free tier.
- **Status:** Active but controversial - developers angered by pricing changes (2024 TechCrunch coverage).
- **Links:** https://business.yelp.com/data/products/places-api/

## OpenTable API
- **Data:** Restaurant directory, reservation availability links. Real-time guest and reservation data for partners.
- **API Format:** REST API (Affiliate/Partner program). Directory API for restaurant data. Sandbox environment available.
- **Free Tier:** Initial free access possible during partnership approval (3-4 week process).
- **Pricing:** Not publicly listed. Partnership-based.
- **Limitations:** Users must complete reservations via OpenTable interface - cannot run full reservation flow via API.
- **Data Freshness:** Real-time reservation availability.
- **Relevance:** MEDIUM - Good for "reserve a table" deep-links but cannot embed full booking flow.
- **Status:** Active. Partnership approval required.
- **Links:** https://docs.opentable.com, https://dev.opentable.com

## Resy API
- **Data:** Restaurant reservations, ratings, cuisine info, photos, waitlist status, bookable time slots across 1,900+ cities.
- **API Format:** NO official public API. Reverse-engineered endpoints exist but are unofficial.
- **Free Tier:** N/A.
- **Pricing:** N/A (no official developer program).
- **Relevance:** LOW as a data source due to lack of official API. Deep-link to Resy app is the best option.
- **Status:** No official developer program. Unofficial clients exist on GitHub.

## DoorDash API
- **Data:** Restaurant menus, prices, delivery information.
- **API Format:** Drive API exists but production access is currently restricted with no timeline for certification.
- **Free Tier:** N/A (restricted access).
- **Relevance:** LOW currently due to access restrictions.
- **Status:** Restricted. Third-party alternatives like Nextract offer unofficial data access.

## Uber Eats API
- **Data:** Store/restaurant data, menus, orders. Endpoints for menu retrieval and updates.
- **API Format:** REST API. Endpoints: `GET /eats/stores/{store_id}/menus`.
- **Free Tier:** Developer access available.
- **Pricing:** Partnership-based.
- **Relevance:** MEDIUM - Most accessible of the delivery platform APIs, but designed for restaurant partners, not consumer discovery apps.
- **Status:** Active with official developer documentation.
- **Links:** https://developer.uber.com/docs/eats/introduction

## Zomato API
- **Data:** Previously offered restaurant search, details, reviews, menus, photos.
- **API Format:** Was REST API.
- **Status:** LARGELY DEPRECATED. Public API has been restricted/discontinued in recent years. Not a viable data source for new projects.

## KitchenHub (Aggregator - NEW)
- **Data:** Unified API connecting Uber Eats, DoorDash, Grubhub. Menu sync, order management, real-time analytics across platforms.
- **API Format:** Unified REST API.
- **Relevance:** MEDIUM - Useful if you need cross-platform restaurant/menu data from a single integration.
- **Links:** https://www.trykitchenhub.com/developer

---

# 6. SAFETY & CRIME DATA

## FBI Crime Data API (UCR/NIBRS)
- **Data:** Uniform Crime Reporting data for the US. Incident-based crime data including offense type, time of day, offender/victim demographics, weapon type, location type. National-level estimates for violent/property crimes.
- **API Format:** REST API returning JSON/CSV. Requires data.gov API key. Endpoints: `/incidents/`, `/meta/incidents`.
- **Free Tier:** Completely free (government service).
- **Rate Limits:** Not published.
- **Data Freshness:** Monthly/annual aggregated data. Not real-time.
- **Relevance:** MEDIUM - Good for neighborhood safety scoring but too aggregated for real-time alerts.
- **Status:** Active. BJS NIBRS National Estimates API updated July 2025.
- **Links:** https://cde.ucr.cjis.gov, https://github.com/fbi-cde/crime-data-api

## SpotCrime API
- **Data:** Crime incident data by location.
- **API Format:** API exists but is not open/free. Commercial and research use requires contacting sales.
- **Free Tier:** No public free access.
- **Pricing:** Custom. Email api@spotcrime.com.
- **Relevance:** MEDIUM - Would be useful but access is restricted.
- **Status:** Active but limited access.

## City Open Data Portals
- **Data:** Crime incident reports, 311 calls, building permits, etc. Major cities maintain open data portals with crime APIs.
- **API Format:** Typically Socrata Open Data API (SODA) or CKAN. JSON/CSV/GeoJSON.
- **Free Tier:** Completely free (public government data).
- **Key Portals:**
  - NYC Open Data: https://opendata.cityofnewyork.us
  - Chicago Data Portal: https://data.cityofchicago.org
  - LA Open Data: https://data.lacity.org
  - SF OpenData: https://datasf.org/opendata
- **Data Freshness:** Varies - some daily, some weekly/monthly.
- **Relevance:** HIGH - Free, authoritative, granular crime data. Must be integrated per-city.
- **Status:** Active across 100+ US cities.

## Citizen App
- **Data:** Real-time 911-derived safety alerts, live incident video, crime trends. Available in 60+ US cities. AI-processed from 900+ public radio channels.
- **API Format:** NO PUBLIC API. Consumer app only.
- **2025 Updates:** Partnered with Axon/Fusus for law enforcement integration (April 2025). Official NYC partnership (July 2025) with 3M subscribers.
- **Relevance:** HIGH relevance data but no developer access. Could deep-link to Citizen app.
- **Status:** Active, expanding. No public API.

## GeoSure (NEW - Emerging)
- **Data:** Hyperlocal safety and security intelligence. GIS SaaS covering 400K+ locations globally. Machine learning + geospatial analysis for safety scoring.
- **Relevance:** HIGH - Purpose-built for safety intelligence at the neighborhood level.
- **Status:** Active.
- **Links:** https://geosure.ai

---

# 7. AIR QUALITY & ENVIRONMENT

## AirNow API (US EPA)
- **Data:** Real-time and forecast AQI from 2,500+ monitoring stations across US, Canada, Mexico. PM2.5, PM10, O3, NO2, SO2, CO.
- **API Format:** REST API. Free registration on AirNow website.
- **Free Tier:** Completely free (government service).
- **Pricing:** No paid plans.
- **Data Freshness:** Real-time observations; daily forecasts.
- **Relevance:** HIGH - Essential free air quality data for US cities.
- **Status:** Active.
- **Links:** https://docs.airnowapi.org

## IQAir / AirVisual API
- **Data:** Global air quality data and forecasts. PM2.5, PM10, SO2, NO2, O3, CO. Worldwide coverage.
- **API Format:** REST API.
- **Free Tier:** Community plan - 500 calls/day.
- **Pricing:** Startup $399/mo (100K calls/day), Enterprise $999/mo (1M calls/day).
- **Data Freshness:** Real-time.
- **Relevance:** HIGH - Best option for global air quality coverage.
- **Status:** Active.

## PurpleAir API
- **Data:** Crowd-sourced real-time air quality from low-cost sensors. PM2.5, PM10, AQI. Dense sensor networks in many US cities.
- **API Format:** REST API. Points-based billing system.
- **Free Tier:** Free for your own sensor's data only. No general free tier.
- **Pricing:** Points-based, purchased in advance. Volume discounts.
- **Relevance:** MEDIUM-HIGH - Hyperlocal air quality data, but coverage depends on sensor density.
- **Status:** Active.
- **Links:** https://www2.purpleair.com

## OpenAQ
- **Data:** Open aggregated air quality data from government and research stations globally. PM2.5, PM10, SO2, O3, CO, BC, NO2.
- **API Format:** REST API. Open source platform.
- **Free Tier:** ~300 calls per 5-minute window (~1/sec). Open access.
- **Pricing:** Free for most use. Custom pricing for high-volume commercial use.
- **Data Freshness:** Near real-time from contributing stations.
- **Relevance:** HIGH - Free, global, open data.
- **Status:** Active.
- **Links:** https://openaq.org, https://explore.openaq.org

---

# 8. PARKING

## SpotHero
- **Data:** Parking availability, pricing, reservations across 4,500+ lots. Integrated with Apple CarPlay.
- **API Format:** Developer platform with API access.
- **Free Tier:** Not publicly documented.
- **Pricing:** Partnership-based.
- **Relevance:** HIGH - Direct booking integration for parking.
- **Status:** Active.
- **Links:** https://spothero.com/developers

## ParkWhiz
- **Data:** Parking search, booking, user management. APIs, JS widgets, webhooks, data feeds. Partners include Ticketmaster/Live Nation, Groupon, MSG.
- **API Format:** REST API v4 for trusted partners. Comprehensive integration toolkit.
- **Free Tier:** Not publicly documented. Partnership required.
- **Pricing:** Partnership-based. Contact partnerships@parkwhiz.com.
- **Relevance:** HIGH - Strong event parking integration (Ticketmaster partnership).
- **Status:** Active.
- **Links:** https://developer.parkwhiz.com

## ParkMobile
- **Data:** Street parking, event parking, reservations across 3,000+ US locations. 30M+ users.
- **API Format:** Consumer-focused app. Developer API less prominent.
- **Relevance:** MEDIUM - Large user base but less developer-oriented than SpotHero/ParkWhiz.
- **Status:** Active.

## City Open Parking Data
- **Data:** Many cities publish real-time parking garage availability via open data portals (e.g., SF, Seattle, Chicago).
- **API Format:** REST APIs, SODA, or custom feeds.
- **Free Tier:** Free (public data).
- **Relevance:** HIGH for cities that publish it. Coverage varies widely.

---

# 9. SOCIAL / USER-GENERATED CONTENT

## Reddit API
- **Data:** Subreddit posts, comments, trending topics. Useful for neighborhood insights from local subreddits (r/nyc, r/chicago, etc.).
- **Free Tier:** 100 queries/minute for non-commercial use. Heavily restricted for commercial use since 2023 pricing changes.
- **Pricing:** Opaque. Commercial use requires approval and likely significant cost. Enterprise pricing not publicly listed.
- **Rate Limits:** 100 QPM free tier. OAuth 2.0 required.
- **Relevance:** MEDIUM - Valuable neighborhood sentiment data but commercial access is expensive/unclear.
- **Status:** Active but developer-hostile pricing since 2023.

## X (Twitter) API
- **Data:** Tweets, trends, user data, location-tagged posts.
- **Free Tier:** Extremely limited - ~1 request/15 min for reading, 1,500 tweets/mo posting, no search.
- **Pricing:** Basic $100/mo (10K tweets), Pro $5,000/mo (1M tweets), Enterprise $42,000+/mo. Pay-per-use in closed beta (Dec 2025).
- **Rate Limits:** Tiered by plan, 15-minute windows.
- **Relevance:** LOW-MEDIUM - Local trending data would be useful but cost is prohibitive.
- **Status:** Active but expensive. Pay-per-use model coming.

## Instagram Graph API
- **Data:** Location-tagged posts, business profiles, insights.
- **API Format:** Facebook Graph API. Requires business verification and approved use cases.
- **Free Tier:** Basic usage free with approval.
- **Limitations:** Severely restricted after Cambridge Analytica. Complex approval process. Limited data types.
- **Relevance:** LOW - Too restricted for practical use in a city guide app.
- **Status:** Active but heavily gated.

## TikTok API
- **Data:** Trending local content, video data.
- **API Format:** Limited official API. Mostly for ad partners and approved research.
- **Free Tier:** Very limited.
- **Relevance:** LOW - No practical API access for local content discovery.
- **Status:** Largely restricted for third-party developers.

---

# 10. MAPPING ALTERNATIVES & SUPPLEMENTS

## OpenStreetMap / Overpass API
- **Data:** Community-contributed global map data. POIs, building footprints, roads, trails, land use, amenities. Incredibly detailed in urban areas.
- **API Format:** Overpass API with custom query language (Overpass QL). Nominatim for geocoding. Bulk planet downloads available.
- **Free Tier:** Completely free. Open Database License (ODbL).
- **Rate Limits:** Public servers heavily loaded. No official limits but abuse will get you blocked. Self-hosting recommended for production.
- **Pricing:** Free (data). Self-host or use Geofabrik paid hosting for Overpass.
- **Data Freshness:** Community-updated, often within hours for major cities.
- **Relevance:** HIGH - Free detailed POI and map data. Essential supplement to any mapping solution.
- **Status:** Active, sponsored by TomTom, Microsoft, Esri, Meta.
- **Links:** https://wiki.openstreetmap.org/wiki/Overpass_API

## HERE Maps API
- **Data:** Enterprise mapping, traffic, geocoding, routing. 120M+ POIs in 100+ countries. Search by name, address, coordinates, phone, business category, food type.
- **API Format:** REST APIs. Two tiers: Open (OSM-based, permissive) and Premium (TomTom-based, restrictive).
- **Free Tier:** ~2,500 requests/day (OSM-based API).
- **Pricing:** Pay-as-you-go ~$0.50-0.75/1,000 calls beyond free tier.
- **Data Freshness:** Real-time traffic; regularly updated POIs.
- **Relevance:** HIGH - Strong alternative to Google Maps, especially for European coverage.
- **Status:** Active.

## TomTom API
- **Data:** Maps, routing, traffic, geocoding, search. POI data for 270+ countries. EV charging station data. Batch geocoding (10K at once).
- **API Format:** REST APIs.
- **Free Tier:** Generous - 50,000 free tile requests + 2,500 free non-tile requests per day. Commercial use allowed on free plan.
- **Pricing:** ~$0.75/1,000 requests beyond free tier (credits purchased in advance).
- **Rate Limits:** 5-50 QPS depending on API.
- **Data Freshness:** Real-time traffic; regularly updated POIs.
- **Relevance:** HIGH - Most generous free tier among commercial mapping providers.
- **Status:** Active.
- **Links:** https://developer.tomtom.com

## Apple MapKit JS
- **Data:** Apple Maps tiles, geocoding, search, ETA, directions. Full Apple Maps experience on web (all platforms including Android/Windows).
- **API Format:** JavaScript library + Maps Server REST API. iOS/Android native SDKs.
- **Free Tier:** 250,000 map views + 25,000 service calls per day. Requires $99/yr Apple Developer Program.
- **Pricing:** No per-call charges within daily limits. Contact Apple for higher volume.
- **Data Freshness:** Real-time.
- **Relevance:** HIGH - Very generous free tier, beautiful maps, good privacy story.
- **Status:** Active.
- **Links:** https://developer.apple.com/documentation/mapkitjs

## Google Maps Platform
- **Data:** Most comprehensive global mapping. Maps, Street View, geocoding, directions, Places, traffic.
- **API Format:** REST APIs + JavaScript SDK.
- **Free Tier:** 10,000 free calls/month per SKU (Essentials category). Changed March 2025.
- **Pricing:** $2-$30/1,000 requests depending on API and tier. Automatic volume discounts at 5M+ monthly events. Optional subscription plans.
- **Data Freshness:** Real-time.
- **Relevance:** HIGH - Most comprehensive but most expensive at scale.
- **Status:** Active. Major pricing restructure March 2025.
- **Links:** https://developers.google.com/maps

## Radar.io (EMERGING ALTERNATIVE)
- **Data:** Full-stack location platform: maps, geocoding, routing, geofencing, place visit detection, trip tracking. 1B+ API calls/day processed.
- **API Format:** REST APIs + mobile SDKs (iOS, Android, React Native, Flutter).
- **Free Tier:** Basic plan is free. 14-day Enterprise trial.
- **Pricing:** Up to 90% cheaper than Google Maps. Geocoding $0.50/1K (vs Google $5/1K). Maps $0.50/1K loads (vs Google $7/1K).
- **Data Freshness:** Real-time.
- **Relevance:** HIGH - Cost-effective Google Maps alternative with geofencing (Google lacks this). SOC 2 Type II, GDPR/CCPA compliant.
- **Status:** Active, growing rapidly. Used by Panera, T-Mobile, Zillow.
- **Links:** https://radar.com

---

# 11. ECONOMIC / BUSINESS DATA

## Walk Score API
- **Data:** Walk Score (0-100), Transit Score (0-100), Bike Score. Pedestrian friendliness metrics (population density, block length, intersection density). US and Canada.
- **API Format:** REST API.
- **Free Tier:** No free commercial tier. Subscription required.
- **Pricing:** Custom subscription. Contact sales.
- **Data Freshness:** Scores updated periodically (not real-time).
- **Relevance:** HIGH - Perfect "walkability" metric for a city guide.
- **Status:** Active.
- **Links:** https://www.walkscore.com/professional/research.php

## US Census API
- **Data:** Demographics by area: population, income, education, housing, commuting patterns. American Community Survey data from 2014-2024.
- **API Format:** REST API returning JSON. Also TIGERweb (geographic boundaries) and Geocoder services.
- **Free Tier:** Completely free. API key recommended but not required.
- **Data Freshness:** Annual updates (ACS 1-year), 5-year estimates.
- **Relevance:** HIGH - Essential for neighborhood demographic profiles.
- **Status:** Active. Video tutorials published 2025.
- **Links:** https://www.census.gov/data/developers.html

## BLS API (Bureau of Labor Statistics)
- **Data:** Employment data, Consumer Price Index, unemployment rates, wages by area.
- **API Format:** REST API returning JSON or Excel. V1 (no registration), V2 (registration for higher limits).
- **Free Tier:** Completely free. No registration required for V1.
- **Pricing:** Free (government service).
- **Data Freshness:** Monthly/quarterly/annual depending on series.
- **Relevance:** MEDIUM - Useful for economic context ("this neighborhood has X% unemployment") but not core city guide feature.
- **Status:** Active.
- **Links:** https://www.bls.gov/developers/home.htm

---

# 12. NEW / EMERGING SOURCES (2025-2026)

## FilterLabs Ubiquity Platform (January 2026)
- **Data:** Source-verified, hyperlocal, geotagged insights from conversational, behavioral, and socioeconomic sources worldwide. Agentic AI + human-in-the-loop validation. Raw data feeds and extensible APIs.
- **Relevance:** HIGH - Novel hyperlocal intelligence that traditional providers cannot deliver.
- **Status:** Newly launched (Jan 2026).

## Local Logic (2025-2026)
- **Data:** Hyperlocal, contextualized location intelligence. 36,437 new neighborhoods added in 2025 alone. 5.01 billion API calls processed in 2025. Won Inman's 2025 Best of Proptech (Data & Intelligence).
- **Relevance:** HIGH - Purpose-built neighborhood intelligence at scale.
- **Status:** Active, rapidly growing.
- **Links:** https://locallogic.co

## Factori
- **Data:** Privacy-safe mobility intelligence combining places, people, property, and economic data. Trade area scoring, store expansion optimization.
- **Relevance:** MEDIUM - More enterprise/retail focused, but trade area data could enhance city guide.
- **Status:** Active.
- **Links:** https://factori.ai

## CityData.AI
- **Data:** Urban digital twins combining crowd-sourced data with sensor measurements. Density and movement pattern quantification.
- **Relevance:** HIGH - Directly relevant to crowd-level features in a city guide.
- **Status:** Active.
- **Links:** https://www.citydata.ai

## 3GPP Release 19 Location Services (Dec 2025)
- **Data:** Enhanced telecom-based location intelligence across satellite networks, smart factories, connected vehicles. Tighter AI integration with location services.
- **Relevance:** MEDIUM-LONG TERM - As 5G Advanced rolls out, telecom-based crowd density data will become more accessible.
- **Status:** Standard finalized Dec 2025, implementations ongoing.

---

# RECOMMENDED STACK FOR KROWDGUIDE

## Tier 1: Must-Have (Start Here)
| Category | Recommendation | Why |
|----------|---------------|-----|
| **Mapping** | Radar.io or Mapbox + OSM | 90% cheaper than Google, includes geofencing |
| **Crowd Levels** | BestTime.app | Only affordable real-time venue busyness API |
| **Transit** | GTFS-RT feeds + OpenTripPlanner | Free, real-time, self-hosted routing |
| **Weather** | NWS API (US) + Open-Meteo (global) | Both completely free |
| **Events** | Ticketmaster + Eventbrite | Free tiers cover ticketed + community events |
| **Venues/POIs** | Foursquare v3 + OSM | Rich venue data with free tier |
| **Air Quality** | AirNow (US) + OpenAQ (global) | Free government data |
| **Safety** | City open data portals + FBI API | Free, authoritative crime data |
| **Demographics** | US Census API | Free, comprehensive |

## Tier 2: Enhance (Add When Growing)
| Category | Recommendation | Why |
|----------|---------------|-----|
| **Dining** | Yelp Fusion (if budget allows) | Best restaurant data but $8-15/1K calls |
| **Reservations** | OpenTable affiliate links | Free to link out to reservations |
| **Parking** | SpotHero API | Direct booking integration |
| **Walkability** | Walk Score API | Perfect fit but requires subscription |
| **Minute Weather** | Tomorrow.io | Hyper-local minute-by-minute forecasts |
| **Event Intelligence** | PredictHQ | Demand forecasting layer |

## Tier 3: Premium (At Scale)
| Category | Recommendation | Why |
|----------|---------------|-----|
| **Foot Traffic** | Placer.ai | Deep analytics but expensive |
| **Hyperlocal Intel** | Local Logic or FilterLabs | Emerging best-in-class neighborhood data |
| **Safety** | GeoSure | ML-powered safety scoring |
| **Transit** | Citymapper API or Moovit | Polished multi-modal routing |
| **Urban Analytics** | CityData.AI | Digital twin crowd modeling |

---

## Cost Estimate: MVP (Tier 1 Only)
- **Mapping:** Radar.io free tier = $0
- **Crowd:** BestTime.app = $29-99/mo
- **Transit:** GTFS + OTP self-hosted = server costs only (~$50-100/mo)
- **Weather:** NWS + Open-Meteo = $0
- **Events:** Ticketmaster + Eventbrite = $0
- **Venues:** Foursquare free tier (10K calls/mo) = $0
- **Air/Safety/Census:** Government APIs = $0
- **TOTAL MVP: ~$80-200/month** (plus server hosting)

---

*Research compiled March 2026. Prices and availability subject to change. Always verify current pricing on official websites before committing.*
