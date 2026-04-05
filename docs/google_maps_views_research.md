# Google Maps Mobile Views — Complete Research for Mapbox GL JS v3 Replication

> Research compiled March 2026. Covers Google Maps mobile app (Android/iOS) as of early 2026, including the major March 12, 2026 update (Immersive Navigation + Ask Maps).

---

## Design System Context

Google Maps adopted **Material 3 Expressive** throughout 2025, with a full **sheet-based UI overhaul** rolling out in January-April 2025. Key design tokens:

- **Color palette**: Cooler, bluer tones replaced the older warm palette. Teal accent color (not Material You Dynamic Color). Orange for Food & Drink POIs, purple for museums, green for parks.
- **Typography**: Google Sans / Roboto. Hierarchical sizing with bold place names, medium-weight metadata, light-weight descriptions.
- **Shapes**: Squircle design language (M3 Expressive). Rounded corners on cards, buttons, and previews. Lozenge-shaped action buttons.
- **Elevation**: Card-like containers with slightly darker backgrounds replace horizontal dividers. Sheets always show a sliver of map at the top.
- **Pin redesign (2024-2025)**: Shorter, rounded-bottom pins with white background and colored icon circle inside (replacing old tall narrow pins with uniform color).

---

## 1. Default Map View (Home / Explore)

### Layout
- **Top**: Search bar with profile avatar on the left, overlays the map. Below the search bar: horizontally scrollable **category pills** (Restaurants, Gas, Coffee, Groceries, Hotels, Pharmacies, etc.). Pills change based on context (driving shows Gas/EV Charging/Hotels; walking shows Coffee/Restaurants).
- **Center**: Full-bleed map canvas with POI icons scattered. POIs use category-colored short pins with white backgrounds and colored icon circles.
- **Bottom-right**: Floating Action Button (FAB) — teal, diamond-shaped with directional arrow (recently made smaller). Above FAB: current location button (now squircle-shaped, compass-like icon).
- **Top-right**: Layers button (stacked diamond icon).
- **Bottom**: Three-tab bottom navigation bar: **Explore** | **You** | **Contribute**.
- **Sheet behavior**: The Explore tab shows a minimized bottom sheet. Pulling up expands it with recommendations, trending places, and curated lists. Sheet never fully hides — always maintains a sliver of map visible at top.

### Visual Style
- Map uses light, earthy tones with grey roads (previously yellow), teal water bodies. POI icons are small, category-colored circles on shortened pin stems. Buildings rendered as light grey footprints. Parks are soft green. The overall palette is muted and cool-toned.
- When sheet is minimized: search bar floats at top, category pills below, full map visible.
- When sheet is expanded: covers most of the screen with transparent status bar showing map sliver.

### Interaction
- Tap search bar: transitions to search screen with recent locations and Explore suggestions.
- Tap category pill: filters map to show only that category, results appear in bottom sheet.
- Tap POI on map: mini info card slides up from bottom.
- Pinch/zoom: smooth vector tile rendering, POI density adjusts with zoom level.
- Tap FAB: enter directions mode.
- Tap location button: centers map on current position with blue dot + accuracy circle.

### Data Shown
- POI names (at sufficient zoom), category icons, user's blue location dot, road names, area/neighborhood names, transit station icons.

### Mapbox GL JS v3 Replication
- **Map**: Mapbox Standard Style (default in v3) provides 3D buildings, landmarks, dynamic lighting.
- **Search bar + pills**: Custom HTML overlay positioned absolutely over the map container. Use CSS `position: fixed` or a flex container wrapping the map.
- **Category pills**: Horizontal scrollable `<div>` with pill-shaped buttons. On tap, use Mapbox `queryRenderedFeatures()` or the Mapbox Geocoding/Search API with category filters.
- **POI icons**: Use `map.addLayer()` with `type: 'symbol'` and custom icon sprites matching Google's category colors. Mapbox Maki icons or custom SVGs.
- **FAB + location**: Custom HTML buttons positioned with CSS. Use `map.getCenter()` and `GeolocateControl` for location tracking.
- **Bottom sheet**: Build with a JavaScript library (e.g., `react-spring`, CSS `transform: translateY()` with drag gesture detection). No built-in Mapbox component.
- **Bottom tabs**: Standard HTML/CSS tab bar overlaying the map container.

---

## 2. Search Results View

### Layout
- **Top**: Search bar with query text, back arrow on left. Below: filter pills (Open now, Rating, Price, Distance, etc.).
- **Map area**: Shows red dot markers at matching locations. Selected result gets a larger/highlighted marker.
- **Bottom**: Horizontally scrollable result cards. Each card shows: place photo thumbnail (left), name, star rating (with count), price level ($-$$$$), category, open/closed status with hours, distance. Cards are approximately 120px tall.
- Alternatively: full-list mode where the sheet expands to show a vertical scrollable list of results with the same card format.

### Visual Style
- Red/coral pin markers on map (distinct from the default category-colored pins).
- Result cards have white backgrounds, rounded corners (M3 Expressive), subtle shadow.
- Selected card is highlighted, corresponding pin on map is enlarged.
- Star ratings are gold/amber. "Open" text is green, "Closed" is red.
- Price level shown as grey dollar signs.

### Interaction
- Scroll cards horizontally: map pans to keep visible markers in view.
- Tap card: map zooms to that place, card expands to full place detail.
- Tap pin on map: corresponding card scrolls into view and highlights.
- Pull up card area: transitions to full vertical list view.
- Filter pills: tap to toggle filters, results update in real-time.

### Data Shown
- Place name, photo, rating (stars + count), price level, category label, open/closed status, distance, brief address.

### Mapbox GL JS v3 Replication
- **Red markers**: Use `map.addLayer()` with `type: 'symbol'` or `type: 'circle'`, or use `mapboxgl.Marker` with custom red pin HTML elements.
- **Search API**: Mapbox Search API (v2) or Mapbox Geocoding API for place search. For richer POI data (ratings, hours, photos), you'd need a third-party API (Foursquare, Yelp, or Google Places API).
- **Horizontal card carousel**: Custom HTML/CSS overlay at bottom. Use `scroll-snap-type: x mandatory` for smooth horizontal scrolling.
- **Map-card sync**: Listen to card scroll events, call `map.flyTo()` to center on the corresponding marker. Use marker click events to scroll the card list.
- **Filter pills**: Custom UI; re-query the search API with filter parameters.

---

## 3. Place Detail View (Business Card)

### Layout (top to bottom)
1. **Photo carousel**: Full-width horizontal swipeable photos at top (~40% of screen). Overlaid tab bar: Overview | Reviews | Photos | Updates | About. Photo count badge (e.g., "24 photos").
2. **Place header**: Name (large bold), star rating with count (e.g., "4.5 (2,341)"), price level, category label (e.g., "Italian restaurant").
3. **Quick info row**: Distance, open/closed status with next opening/closing time.
4. **Action buttons row** (now anchored at bottom of screen): Directions | Start | Ask (Gemini) | Call | Save | Share — horizontally scrollable, lozenge-shaped buttons with icons.
5. **Info sections** (M3 Expressive card containers with darker backgrounds):
   - **Address** with map snippet
   - **Hours** (expandable, shows full week)
   - **Phone number** (tap to call)
   - **Website** (tap to open)
   - **Menu** link (for restaurants)
   - **Accessibility** info (wheelchair icon)
6. **Popular Times**: Bar chart showing hourly busyness. Blue bars = typical, red bar overlay = live current busyness. Day-of-week selector. Tap any bar for description ("Usually not too busy").
7. **AI Review Summary**: Gemini-generated summary of reviews highlighting key themes (food quality, ambiance, service). "Know Before You Go" section.
8. **Reviews section**: Individual review cards with user avatar, name, rating, date, text, photos.
9. **"People also search for"**: Horizontal scroll of related place cards.
10. **Suggest an edit / Add your business**: Styled as prominent M3 buttons.

### Visual Style
- Tabs sit above the photo carousel (recent change). Card containers use slightly darker background instead of divider lines.
- Action buttons are lozenge-shaped with teal/blue icons, anchored at screen bottom for one-handed access.
- Popular Times chart: blue bars (historical), red bar + red box (live), grey bars (closed hours). Interactive — can tap to see description per hour.
- Rating stars are amber/gold. Category text is grey. Open = green, Closed = red.

### Interaction
- Swipe photos horizontally. Tap photo to enter fullscreen gallery.
- Tap tabs to switch between Overview/Reviews/Photos/Updates/About.
- Action buttons are always accessible (anchored bottom).
- Tap "Directions" to enter navigation mode.
- Tap "Save" to add to a list (shows list picker).
- Pull down to dismiss and return to map.

### Data Shown
- Photos, name, rating, review count, price level, category, address, hours, phone, website, menu, popular times histogram, AI review summary, individual reviews, related places.

### Mapbox GL JS v3 Replication
- **Place data**: Google Places API (or Foursquare/Yelp API) for business details, photos, reviews, popular times.
- **Photo carousel**: Swiper.js or custom CSS scroll-snap carousel.
- **Action buttons**: Fixed-position HTML bar at bottom with SVG icons.
- **Popular times chart**: Chart.js or D3.js bar chart. Custom component — no map API needed.
- **Sheet behavior**: CSS/JS bottom sheet that expands from partial to full height. On partial: shows place header + action buttons. On full: shows all sections.
- **Map interaction**: When place detail is shown, map zooms to place location with a marker. Tapping "Directions" triggers Mapbox Directions API.
- **AI summaries**: Would require your own LLM integration or pre-computed summaries.

---

## 4. Navigation View (Turn-by-Turn)

### Pre-March 2026 (Traditional 2D)
- **Top card**: Next maneuver icon (arrow shape) + street name + distance to maneuver. Below: subsequent maneuver preview.
- **Map**: Tilted forward-facing 2D map, auto-rotating to heading. Blue route polyline with traffic coloring (green/orange/red segments). Grey polylines for alternate routes.
- **Bottom bar**: ETA, distance remaining, arrival time. "X" button to exit navigation.
- **Bottom-left**: Speed indicator showing current speed (speed limit nearby).
- **Lane guidance**: Visual lane indicator at top showing which lanes to be in, highlighted in blue.
- **"Approaching destination"**: Final card shows destination name, shows Street View preview.
- **Simplified map**: Non-essential POIs hidden, buildings dimmed, route and immediate surroundings highlighted.

### Post-March 2026 (Immersive Navigation — 3D)
- **3D rendering**: Full 3D buildings, overpasses, terrain along the route. Wireframe/abstracted aesthetic (not photorealistic) to reduce visual noise.
- **Camera**: Tilted down more than before, revealing 3D environment.
- **Dynamic X-ray views**: Buildings become transparent ahead of tricky turns to maintain sight lines.
- **Smart zoom**: Camera pulls back to show broader view before complex maneuvers, zooms in for simple stretches.
- **Lane-level detail**: Traffic lights, crosswalks, stop signs, lane markings rendered as visual 3D elements rather than text.
- **Voice guidance**: Landmark-based ("Go past this exit and take the next one for Illinois 43 South") instead of distance-based.
- **Route line**: Blue polyline persists, with occlusion behind 3D buildings/bridges/trees.
- **Destination arrival**: Street View previews, parking guidance, building entrance highlighting.
- **Alternate routes**: Shown as greyed polylines with tradeoff info (tolls vs. traffic).
- **Real-time alerts**: Community-contributed incident markers along route.

### Visual Style
- 3D mode: Muted building colors (grey/beige wireframe), prominent blue route line, highlighted road details (lane markings, crosswalks). Dynamic lighting based on time of day.
- Speed indicator is a small circle showing current speed with speed limit nearby.
- Maneuver card at top has dark/semi-transparent background for contrast.
- Bottom bar is compact: ETA left, distance center, arrival time right.

### Interaction
- Tap map: briefly shows overview controls, then returns to navigation.
- Swipe up on bottom bar: shows route overview with full route visible.
- Tap alternate route: switches to it (polyline turns blue).
- Tap "X": exits navigation with confirmation.
- Automatic re-routing when deviation detected.

### Mapbox GL JS v3 Replication
- **Route line**: Mapbox Directions API for route geometry. Render with `map.addLayer({ type: 'line' })` using the route GeoJSON. GL JS v3 supports route lines with borders natively.
- **3D buildings along route**: Mapbox Standard Style includes 3D buildings. Use `map.setLayoutProperty()` to show/hide buildings. For transparency/x-ray effect, modify `fill-extrusion-opacity` dynamically based on camera bearing.
- **Camera animation**: Use `map.easeTo()` or `map.flyTo()` with `pitch`, `bearing`, and `zoom` to simulate forward-facing tilted navigation view. Continuously update as user moves along route.
- **Maneuver cards**: Custom HTML overlay. Parse Mapbox Directions API response for `steps[]` with `maneuver.instruction`, `maneuver.type`, `distance`.
- **Speed/ETA bar**: Custom HTML. Calculate from Directions API `duration` and `distance` fields.
- **Lane guidance**: Mapbox Directions API returns `intersections[].lanes` data. Render as custom HTML lane indicator.
- **Traffic coloring**: Use `mapbox/driving-traffic` profile. Directions API returns `congestion` or `congestion_numeric` per route leg. Color-code line segments accordingly.
- **Turn-by-turn simulation**: Use `turf.along()` to animate a marker along the route line, updating camera position at each step.
- **Limitations**: True 3D Immersive Navigation with wireframe buildings and x-ray views would require significant custom WebGL work beyond standard Mapbox capabilities.

---

## 5. Immersive View / 3D View (Place Exploration)

### How It Works
- Available for select cities and places. Shows a 3D flyover model of the location.
- **Time slider**: Scrub through different times of day to preview lighting conditions and weather (sun position, cloud cover).
- **Busyness overlay**: Buildings and areas show color-coded busyness at different times.
- **Transition**: User taps "Immersive View" from a place detail card. Camera smoothly transitions from 2D overhead to a tilted 3D aerial view, zooming into photorealistic 3D city models.
- **Indoor views**: Some restaurants and venues show interior views navigable in 3D.
- Built from Street View imagery + aerial photography, reconstructed using AI/photogrammetry.

### Visual Style
- Photorealistic 3D city model with accurate building geometry, trees, roads.
- Atmospheric effects: sun position changes with time slider, shadows move accordingly.
- Busyness shown as colored heatmap overlays on buildings/areas.
- Smooth camera orbiting and tilting.

### Interaction
- Pinch to zoom. Drag to orbit. Two-finger tilt to change viewing angle.
- Time slider at bottom: drag to see different times of day.
- Tap on a place within the 3D view to see its detail card.

### Mapbox GL JS v3 Replication
- **3D buildings**: Mapbox Standard Style provides 3D extruded buildings with dynamic lighting (AmbientLight + DirectionalLight APIs in v3).
- **Time-of-day lighting**: Use v3 experimental lighting APIs to change sun position, shadow direction based on a time slider control.
- **Photorealistic 3D**: Not directly possible. Mapbox provides extruded building footprints with landmark 3D models, but not photorealistic reconstruction. Could supplement with custom 3D models (GLTF) loaded via `map.addLayer({ type: 'model' })`.
- **Busyness overlay**: Use `map.addLayer({ type: 'fill-extrusion' })` with data-driven `fill-extrusion-color` based on busyness data.
- **Camera orbit**: Use `map.easeTo()` with changing `bearing` in a `requestAnimationFrame` loop.
- **Time slider**: Custom HTML range input. On change, update lighting properties and overlay data.

---

## 6. Street View / Live View (AR)

### Street View
- **Panoramic 360-degree imagery** at street level.
- Access: Tap the Street View preview (now squircle-shaped, M3 Expressive) on a place card, or tap the small person icon and drag onto the map.
- **UI**: Fullscreen panorama. Navigation arrows on the ground to move forward/backward. Address/location bar at bottom. Mini-map in corner showing position and viewing direction.
- **Transition**: Smooth zoom-in animation from overhead map to street level.

### Live View (AR Walking Navigation)
- **Camera feed**: Full-screen phone camera view.
- **AR overlays**: Large floating arrows on the ground/sidewalk showing direction. Distance markers. Turn indicators at intersections.
- **Mini-map**: Small map at bottom of screen showing traditional route view.
- **Landmarks**: AR markers on nearby landmarks with names and distances.
- **Search with Live View**: Lift phone to see AR-overlaid POI markers (ATMs, restaurants, parks) with ratings, open/closed status, and distance.
- **Indoor Live View**: AR arrows inside airports, train stations, and malls (1,000+ venues).
- **Safety**: Road crossing overlay warns users to check before crossing.
- Works via Visual Positioning System (VPS) matching camera feed to Street View imagery.

### Mapbox GL JS v3 Replication
- **Street View**: Not available in Mapbox. Would need: Mapillary (owned by Meta) for street-level imagery, or custom photosphere integration. No built-in panoramic viewer.
- **AR Live View**: Requires native mobile app with camera access (ARKit/ARCore). Not possible in a web browser with Mapbox GL JS alone. Would need: WebXR API + custom AR rendering, or a native mobile app using Mapbox Navigation SDK + AR framework.
- **Mini-map**: Can create a small Mapbox map instance in a corner overlay showing the route.
- **Practical alternative**: For a city guide web app, skip Street View/AR and focus on photo galleries and detailed map views instead.

---

## 7. Transit View

### Layout
- **Map overlay**: Colored transit lines rendered on top of the base map. Each transit system/line has a distinct color matching real-world branding.
- **Station markers**: Circle icons at station locations with transit line color. Tap to see station details (lines served, real-time arrivals).
- **Route comparison**: When searching for directions, transit tab shows multiple route options: Walk, Transit, Drive, Ride. Each option shows total time, departure time, and transfers.
- **Transit directions**: Step-by-step with walking segments (dotted line) and transit segments (colored line matching the transit line). Transfer points marked.
- **Real-time arrivals**: Station cards show live departure countdown (e.g., "3 min" with live indicator).
- **Crowdedness**: Station cards may show crowd level indicator.

### Visual Style
- Transit lines use official route colors overlaid on the map.
- Station icons: small circles with line color, or multi-colored for transfer stations.
- Route comparison cards: white background, transit line color accent, mode icons (bus/train/walk).
- Walking segments shown as grey dotted lines. Transit segments as solid colored lines.

### Interaction
- Tap "Transit" in the layers menu to toggle transit overlay on/off.
- Tap a station on the map to see departures.
- In directions mode: tap transit tab, select route option, see step-by-step.
- Alternate departures: if you miss a train, swipe to see next available.

### Mapbox GL JS v3 Replication
- **Transit lines overlay**: No built-in transit layer. Options:
  - Use GTFS data from transit agencies. Parse route shapes and render as `map.addLayer({ type: 'line' })` with agency-specific colors.
  - Mapbox has a transit overlay for some cities in the Standard style, but it's limited.
- **Station markers**: Plot GTFS stop data as `type: 'circle'` or `type: 'symbol'` layers.
- **Real-time arrivals**: Consume GTFS Realtime feeds. Display in custom HTML popups on station tap.
- **Route planning**: Use Mapbox Directions API (limited transit support) or integrate a transit-specific API (Google Directions, OpenTripPlanner, Transitland).
- **Crowdedness**: Would need third-party data source.

---

## 8. Nearby / Explore View

### Layout
- Accessed via **Explore tab** at bottom, or by tapping the search bar.
- **Category grid/list**: Food & Drink, Shopping, Services, Entertainment, Outdoors, etc. Each category has an icon.
- **Subcategories**: Under Food & Drink: Restaurants, Cafes, Bars, Fast Food, etc.
- **Recommendation cards**: Personalized based on time of day, location, past behavior. Cards show photo, name, rating, distance, open/closed.
- **"Popular nearby" section**: Trending places with photos.
- **Time-filtered results**: "Open now," "Popular right now" filters at top.
- **Curated lists**: "Best brunch spots," "Top-rated sushi," etc. — editorial and AI-curated.
- **Trending on Maps**: Places gaining popularity.

### Visual Style
- Category icons are colorful and rounded. Cards are M3 Expressive style with rounded corners, photo thumbnails, subtle shadows.
- "Open now" badge is green. "Popular right now" has a flame or trending icon.
- The explore feed looks like a social-media-style vertical scroll of cards.

### Interaction
- Scroll vertically through recommendations.
- Tap category to see filtered results on map + list.
- Tap card to go to place detail view.
- Pull down to refresh recommendations.
- Time-of-day context automatically changes recommendations (morning: coffee/breakfast; evening: dinner/bars).

### Mapbox GL JS v3 Replication
- **Category data**: Foursquare Places API, Yelp Fusion API, or Google Places API for nearby POIs with categories.
- **Category grid**: Custom HTML/CSS grid overlay. On tap, query API with category filter and update map markers.
- **Recommendation feed**: Custom UI component. Personalization requires user behavior tracking backend.
- **Time filtering**: Filter API results by `open_now` parameter. "Popular right now" requires a busyness data source.
- **Curated lists**: Would need editorial backend or AI-generated list content.

---

## 9. Saved Places / Lists

### Layout
- Accessed via **You tab** in bottom navigation.
- **Default lists**: Favorites (heart icon), Want to go (bookmark), Starred places (star). Each shows count.
- **Custom lists**: User-created with custom name and emoji icon.
- **List view**: Vertical scroll of saved places. Each entry shows photo carousel snippet, name, rating, category, notes.
- **Map view**: Toggle to see all saved places on the map with colored/styled pins matching list.
- **Nearby saved**: Horizontal card carousel showing saved places within 25km.
- **Sharing**: Share list via link or QR code. Collaborative editing with invited editors.

### Visual Style
- List icons are emoji-based. Default lists have standard icons (heart, bookmark, star).
- Saved places appear on the main map with small colored markers matching their list.
- Photo carousel snippets show horizontally scrollable thumbnails.
- Cards in the You tab use the sheet-based layout with map sliver at top.

### Interaction
- Tap "Save" on any place: shows list picker popup (which list to add to).
- Tap list: see all places in that list as a scrollable list or on a map.
- Long-press a place in a list: options to remove, move, add note.
- Share: generates a link; recipients can "follow" the list to see pins on their map.
- Notes: up to 4,000 characters per place.

### Mapbox GL JS v3 Replication
- **Saved places storage**: Local storage, IndexedDB, or backend database per user.
- **List UI**: Custom HTML/CSS list component with drag-and-drop for reordering.
- **Map markers for saved places**: Use `mapboxgl.Marker` or a GeoJSON source + symbol layer. Style markers per list (different colors/icons).
- **Sharing**: Generate shareable URLs with list IDs. Backend API to serve shared list data.
- **Save button**: Custom popup on place cards with list selector.

---

## 10. Timeline / Your Activity

### Layout
- Accessed via profile menu > **Your Timeline**.
- **Day view**: Shows a timeline of places visited on a specific date. Each entry has: place name, time spent, photos taken there, travel mode between places (walking/driving/transit).
- **Trips tab**: Groups multi-day travel into trips with venue lists, distances traveled.
- **Places tab**: All visited places grouped by category (Shopping, Hotels, Food & Drink, Attractions, Airports).
- **Cities tab**: Cities visited, with last visit date and place count.
- **Map visualization**: Route traces on the map for a selected day, with pins at visited locations.

### Visual Style
- Timeline entries are vertical cards connected by dotted line (travel segments).
- Mode icons (car, walking, bus) between entries.
- Photos inline with timeline entries.
- Map shows colored route traces for the day.

### Recent Changes (2025)
- **On-device storage only**: Google moved all Timeline data to device-local storage (no web version).
- **Encrypted cloud backup**: Optional, toggled via cloud icon in top-right.
- **Auto-delete**: Default 3 months. Configurable.
- **Edit capability**: Can edit locations and times. Can delete entries.

### Mapbox GL JS v3 Replication
- **Route visualization**: Render GPS traces as `map.addLayer({ type: 'line' })` with timestamp-based coloring.
- **Place pins**: Plot visited locations as markers with timestamps.
- **Timeline UI**: Custom vertical timeline component in HTML/CSS.
- **Data source**: Would need location tracking (Geolocation API with user consent) and place matching.
- **Privacy**: Must handle all data client-side or with encrypted storage per Google's approach.

---

## 11. Offline Maps

### Layout
- Accessed via profile menu > **Offline maps**.
- **Area selector**: Map with a draggable blue rectangle overlay. Pan and zoom to cover desired area.
- **Download size estimate**: Shown below the rectangle (e.g., "245 MB").
- **Recommended maps**: Suggested areas based on upcoming travel.
- **Downloaded maps list**: Shows each saved area with name, size, last updated date, and options to Update/Delete/Rename.
- **Storage options**: Choose internal storage or SD card (Android).

### Interaction
- Tap "Select your own map" > adjust rectangle > tap "Download."
- Or search for a city > three-dot menu > "Download offline map."
- Auto-update toggle: refreshes maps every ~2 weeks.

### Limitations Offline
- No transit, bicycling, or walking directions.
- No real-time traffic.
- Driving directions use estimated travel times (no congestion data).

### Mapbox GL JS v3 Replication
- **Offline maps**: Mapbox GL JS supports offline via Service Workers + cache API. The `mapbox-gl-js` library can cache tiles.
- **Mapbox Mobile SDKs**: Native SDKs have `OfflineManager` for downloading regions. Better for mobile apps.
- **For web**: Use Mapbox's tile caching with a Service Worker. Define bounds to pre-cache. Store in IndexedDB.
- **Area selector UI**: Custom HTML overlay with draggable rectangle (Leaflet-style area selector adapted for Mapbox).
- **Practical approach**: For a PWA city guide, pre-cache specific city tiles on first visit or during onboarding.

---

## 12. Layer Selector

### Layout
- Tap the **layers button** (top-right, stacked diamond icon).
- **Two sections**: "Map type" and "Map details."
- **Map types**: Default | Satellite | Terrain — shown as preview thumbnails.
- **Map details** (toggles): Traffic | Transit | Biking — can layer on top of any map type.
- Tapping a map type changes the base layer. Tapping a detail toggles the overlay.

### Visual Style
- Layer picker is a floating panel/sheet with rounded corners.
- Map type options shown as square thumbnail previews with labels.
- Detail options shown as toggle pills or icons.
- Satellite option sometimes shows hybrid with labels overlay.

### Traffic Layer Colors
- Green: no delays. Orange: medium traffic. Red: traffic delays (darker red = slower).

### Biking Layer Colors
- Dark green: trails (no auto traffic). Green: dedicated bike lanes. Dotted green: bicycle-friendly roads. Brown: unpaved/dirt paths.

### Mapbox GL JS v3 Replication
- **Map types**: Switch Mapbox style URLs:
  - Default: `mapbox://styles/mapbox/standard` (v3 default with 3D)
  - Satellite: `mapbox://styles/mapbox/satellite-streets-v12`
  - Terrain: Custom style with terrain/hillshade layers enabled
- **Traffic overlay**: `map.addSource()` with Mapbox Traffic tileset + `map.addLayer({ type: 'line' })` with color-coded congestion.
- **Transit overlay**: Custom GTFS layer (see Transit View section).
- **Biking overlay**: Custom layer from cycling infrastructure data (OpenStreetMap cycling tags or Mapbox cycling-specific tilesets).
- **Layer picker UI**: Custom floating HTML panel with thumbnail previews. Use `map.setStyle()` or `map.setLayoutProperty()` to toggle layers.

---

## 13. Recent Updates (2025-2026)

### Ask Maps (March 2026)
- **Conversational AI** powered by Gemini. Type natural-language questions in the search bar (e.g., "cozy dinner spot with outdoor seating for 4 tonight").
- Returns curated AI-generated responses with place cards, directions, review summaries, and follow-up capability.
- Personalized using saved places, search history, and preferences.
- Analyzes 300M+ places and 500M+ user contributions.
- Rolling out in US and India, Android and iOS.
- No ads currently, but not ruled out for the future.

### Immersive Navigation (March 2026)
- 3D driving directions with wireframe/abstracted building rendering.
- Built from Street View + aerial imagery analyzed by Gemini.
- Smart zoom, transparent buildings, landmark-based voice guidance.
- Rolling out in the US across smartphones, CarPlay, Android Auto.

### Gemini Integration Timeline
- **November 2025**: Gemini replaced Google Assistant in Maps navigation voice.
- **November 2025**: "Know Before You Go" feature with structured review content.
- **December 2025**: Gemini app surfaced richer Google Maps results.
- **January 2026**: Gemini expanded to walking and cycling navigation.
- **March 2026**: Immersive Navigation + Ask Maps.

### Icon Redesign (Late 2025 - Early 2026)
- Gradient icon refresh. Google Maps icon now uses gradient version of the familiar pin design.
- Part of broader Google design language shift emphasizing AI-driven innovation.

### EV Charging Layer
- Charging station markers on map. Filter by connector type, charging speed.
- In Android Automotive vehicles: charging stops auto-added to routes, live plug availability in 28 European countries.
- Mapbox also now supports EV routing in its Directions API (battery prediction, automatic charging stop insertion).

### Wheelchair Accessible Routes
- Accessible Places feature: wheelchair icon on accessible business profiles. Available globally.
- Wheelchair-accessible walking paths and stair-free navigation routes.
- Accessible seating, restrooms, and parking info in place details.

### Weather
- Limited native integration. Time slider in Immersive View shows weather/lighting preview.
- No real-time weather layer on the main map (unlike some weather-specific apps).

### Material 3 Expressive (Throughout 2025)
- Card containers replacing divider lines.
- Squircle shapes (Street View preview, buttons).
- Action carousel anchored to bottom.
- Sheet-based navigation across all tabs.
- Settings page getting M3 Expressive makeover (still in progress).

---

## Cross-Cutting: Mapbox GL JS v3 Architecture for a City Guide App

### Recommended Stack
```
Mapbox GL JS v3 (Standard Style)
  + Custom HTML/CSS overlay system
  + Bottom sheet component (custom or react-spring)
  + Mapbox Directions API (routing)
  + Mapbox Search/Geocoding API (search)
  + Third-party POI API (Foursquare/Google Places for rich data)
  + Chart.js or D3.js (popular times, analytics)
  + Custom marker system (SVG pins with category colors)
```

### Key Mapbox v3 Features to Leverage
1. **Standard Style**: 3D buildings + landmarks + dynamic lighting out of the box.
2. **WebGL2 rendering**: 60fps on mobile and desktop.
3. **Route lines with borders**: Native support in v3.
4. **Experimental lighting APIs**: AmbientLight + DirectionalLight for time-of-day effects.
5. **Fill-extrusion layer**: For custom 3D building styling and busyness overlays.
6. **GeolocateControl**: Built-in user location tracking with heading indicator.
7. **NavigationControl**: Built-in zoom/compass controls.
8. **Custom layers API**: For advanced WebGL rendering if needed.

### What You Must Build Custom
1. **Bottom sheet** (Google's signature interaction pattern)
2. **Search bar + category pills** overlay
3. **Place detail cards** with photo carousels
4. **Navigation HUD** (maneuver cards, ETA bar, speed display)
5. **Layer picker** floating panel
6. **Saved places / lists** system with sharing
7. **Popular times** bar chart component
8. **Explore feed** with personalized recommendations

### What's Not Possible to Replicate
1. **Photorealistic Immersive View** (Google's 3D city reconstruction from Street View)
2. **Street View panoramas** (proprietary Google data; Mapillary is a partial alternative)
3. **AR Live View** (requires native app with camera + ARKit/ARCore)
4. **Ask Maps conversational AI** (requires custom LLM integration)
5. **Popular Times live data** (proprietary Google data; no public API)
6. **Gemini-powered review summaries** (requires your own AI pipeline)

---

## Sources

- [Android Authority: Google Maps UI Changes](https://www.androidauthority.com/google-maps-ui-3590494/)
- [9to5Google: Google Maps Sheet Redesign](https://9to5google.com/2025/04/24/google-maps-sheet-redesign-android/)
- [9to5Google: Material 3 Expressive Redesigns](https://9to5google.com/2025/11/17/google-material-3-expressive-redesign/)
- [9to5Google: Immersive Navigation](https://9to5google.com/2026/03/12/google-maps-immersive-navigation/)
- [Fast Company: Google Maps Navigation Redesign](https://www.fastcompany.com/91506736/the-new-google-maps-redesign-aims-to-keep-your-eyes-on-the-road-not-your-screen)
- [Google Blog: Ask Maps and Immersive Navigation](https://blog.google/products-and-platforms/products/maps/ask-maps-immersive-navigation/)
- [Android Police: Place Information Card Redesign](https://www.androidpolice.com/google-maps-new-look-listing-pages/)
- [Android Police: Carousel Interface Update](https://www.androidpolice.com/google-maps-carousel-interface-update/)
- [Google: Places UI Kit](https://mapsplatform.google.com/resources/blog/introducing-places-ui-kit-a-low-code-way-to-display-googles-places-content-on-your-map-of-choice/)
- [Mapbox GL JS v3 Blog](https://www.mapbox.com/blog/maps-sdks-new-versions)
- [Mapbox 3D Buildings Example](https://docs.mapbox.com/mapbox-gl-js/example/3d-buildings/)
- [Mapbox GL Directions Plugin](https://docs.mapbox.com/mapbox-gl-js/example/mapbox-gl-directions/)
- [UX Planet: Google Maps vs Apple Maps](https://uxplanet.org/google-maps-vs-apple-maps-subtle-ux-choices-that-shape-how-we-navigate-a58a1c60ad10)
- [Figma: Google Maps UI Views (2024)](https://www.figma.com/community/file/1352319963071516110/google-maps-ui-views-for-mobile-2024)
- [Tom's Guide: Google Maps Live View vs Apple Maps](https://www.tomsguide.com/computing/mobile-apps/i-tested-apple-maps-guide-me-vs-google-maps-live-view-which-map-app-has-the-better-ar-navigation)
- [Google Support: Layers](https://support.google.com/maps/answer/3092439?hl=en&co=GENIE.Platform%3DAndroid)
- [Google Support: Offline Maps](https://support.google.com/maps/answer/6291838?hl=en&co=GENIE.Platform%3DAndroid)
- [Google Support: Timeline](https://support.google.com/maps/answer/6258979?hl=en&co=GENIE.Platform%3DAndroid)
- [Google Support: Popular Times](https://support.google.com/business/answer/6263531?hl=en)
- [Google Blog: Immersive View for Routes](https://blog.google/products-and-platforms/products/maps/google-maps-immersive-view-routes/)
- [BrandXR: Google Maps AR Navigation Guide](https://www.brandxr.io/mastering-google-maps-ar-navigation-and-live-view-a-complete-guide)
- [ALM Corp: Google Maps 2026 Update](https://almcorp.com/blog/google-maps-new-icon-gemini-features-2026/)
- [Geeky Gadgets: Google Maps Gemini Navigation](https://www.geeky-gadgets.com/google-maps-gemini-navigation/)
