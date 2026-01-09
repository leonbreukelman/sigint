# SIGINT Map Integration Guide

## Files Created
1. `frontend/map.js` - Leaflet map controller with location extraction
2. `frontend/map.css` - Dark theme styling matching SIGINT aesthetic

## Required Changes to index.html

### 1. Add Leaflet CSS & JS to <head>
```html
<!-- Leaflet CSS -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" 
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" 
      crossorigin=""/>

<!-- Your existing styles -->
<link rel="stylesheet" href="styles.css">
<link rel="stylesheet" href="map.css">
```

### 2. Add Leaflet JS before closing </body>
```html
<!-- Leaflet JS -->
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
        crossorigin=""></script>

<!-- Your existing scripts -->
<script src="map.js"></script>
<script src="app.js"></script>
```

### 3. Add Map Section HTML (place ABOVE the grid container)
```html
<!-- World Map Section -->
<section class="map-section">
    <div class="map-header">
        <div class="map-title">
            <span class="map-title-icon">🌍</span>
            <span>GLOBAL INTELLIGENCE MAP</span>
        </div>
        <div class="map-controls">
            <span id="map-counter" class="map-counter">0 LOCATIONS</span>
            <button id="map-toggle" class="map-toggle">▲ COLLAPSE MAP</button>
        </div>
    </div>
    <div id="map-container">
        <div id="sigint-map"></div>
    </div>
</section>

<!-- Your existing grid -->
<div class="grid">
    ...
</div>
```

## Changes to app.js

### Initialize the map on load
```javascript
// At the top of your app.js, after DOM loads:
let sigintMap;

document.addEventListener('DOMContentLoaded', () => {
    sigintMap = new SigintMap();
    sigintMap.init();
    
    // Your existing initialization...
    loadAllCategories();
});
```

### Update the map when data loads
```javascript
// In your loadCategory() or wherever you handle API responses:
async function loadCategory(category) {
    const data = await fetchCategoryData(category);
    
    // Your existing rendering code...
    renderCategoryGrid(category, data);
    
    // Update map markers
    if (sigintMap) {
        sigintMap.updateMarkers(allCategoriesData);
    }
}
```

## Features Included

✅ **CartoDB Dark tiles** - Matches your terminal aesthetic
✅ **Auto location extraction** - Scans titles/summaries for 100+ countries/cities
✅ **Category-colored markers** - Red (Geopolitical), Green (AI/ML), etc.
✅ **Pulsing markers** - Subtle animation
✅ **Collapsible panel** - Toggle button to hide/show
✅ **Click popups** - Shows title, category, location, read more link
✅ **Responsive** - Works on mobile

## Location Coverage

The system recognizes 100+ locations including:
- Major countries (US, Russia, China, Ukraine, Iran, Israel, etc.)
- Key cities (Washington, Beijing, Moscow, London, etc.)
- Regions (Middle East, NATO, EU, etc.)
- Strategic locations (Pentagon, Kremlin, Silicon Valley, etc.)

## How It Works

1. When news items load, `map.js` scans each title + summary
2. Matches against location database (case-insensitive)
3. Creates colored marker at coordinates
4. Groups all markers in a layer
5. Updates counter showing total locations

## Next Steps

1. Test locally by opening index.html
2. Verify map renders with dark tiles
3. Check that markers appear when news loads
4. Adjust map height in CSS if needed (currently 280px)

## Future Enhancements

- Backend location extraction using NER (Named Entity Recognition)
- Marker clustering for dense regions
- Heat maps for activity levels
- Arc lines showing connections between events
- Time-based filtering (show events from last 24h, etc.)
