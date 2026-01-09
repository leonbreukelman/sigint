/**
 * SIGINT World Map - Leaflet + CartoDB Dark
 */

// Location database for geo-extraction
const LOCATIONS = {
    // Countries
    'ukraine': [48.3794, 31.1656], 'russia': [61.524, 105.3188], 'china': [35.8617, 104.1954],
    'taiwan': [23.6978, 120.9605], 'iran': [32.4279, 53.688], 'israel': [31.0461, 34.8516],
    'gaza': [31.3547, 34.3088], 'palestine': [31.9522, 35.2332], 'lebanon': [33.8547, 35.8623],
    'syria': [34.8021, 38.9968], 'iraq': [33.2232, 43.6793], 'saudi arabia': [23.8859, 45.0792],
    'yemen': [15.5527, 48.5164], 'north korea': [40.3399, 127.5101], 'south korea': [35.9078, 127.7669],
    'japan': [36.2048, 138.2529], 'india': [20.5937, 78.9629], 'pakistan': [30.3753, 69.3451],
    'afghanistan': [33.9391, 67.71], 'turkey': [38.9637, 35.2433], 'germany': [51.1657, 10.4515],
    'france': [46.2276, 2.2137], 'uk': [55.3781, -3.436], 'britain': [55.3781, -3.436],
    'united states': [37.0902, -95.7129], 'us': [37.0902, -95.7129], 'usa': [37.0902, -95.7129],
    'america': [37.0902, -95.7129], 'canada': [56.1304, -106.3468], 'mexico': [23.6345, -102.5528],
    'brazil': [-14.235, -51.9253], 'argentina': [-38.4161, -63.6167], 'australia': [-25.2744, 133.7751],
    'europe': [54.526, 15.2551], 'africa': [-8.7832, 34.5085], 'asia': [34.0479, 100.6197],
    'middle east': [29.2985, 42.551], 'nato': [50.8476, 4.3572], 'eu': [50.8503, 4.3517],
    'european union': [50.8503, 4.3517], 'un': [40.7489, -73.968], 'united nations': [40.7489, -73.968],
    'philippines': [12.8797, 121.774], 'vietnam': [14.0583, 108.2772], 'indonesia': [-0.7893, 113.9213],
    'malaysia': [4.2105, 101.9758], 'singapore': [1.3521, 103.8198], 'thailand': [15.87, 100.9925],
    'myanmar': [21.9162, 95.956], 'bangladesh': [23.685, 90.3563], 'sri lanka': [7.8731, 80.7718],
    'nepal': [28.3949, 84.124], 'poland': [51.9194, 19.1451], 'romania': [45.9432, 24.9668],
    'hungary': [47.1625, 19.5033], 'czech': [49.8175, 15.473], 'slovakia': [48.669, 19.699],
    'austria': [47.5162, 14.5501], 'switzerland': [46.8182, 8.2275], 'italy': [41.8719, 12.5674],
    'spain': [40.4637, -3.7492], 'portugal': [39.3999, -8.2245], 'netherlands': [52.1326, 5.2913],
    'belgium': [50.5039, 4.4699], 'sweden': [60.1282, 18.6435], 'norway': [60.472, 8.4689],
    'finland': [61.9241, 25.7482], 'denmark': [56.2639, 9.5018], 'greece': [39.0742, 21.8243],
    'egypt': [26.8206, 30.8025], 'libya': [26.3351, 17.2283], 'tunisia': [33.8869, 9.5375],
    'algeria': [28.0339, 1.6596], 'morocco': [31.7917, -7.0926], 'south africa': [-30.5595, 22.9375],
    'nigeria': [9.082, 8.6753], 'kenya': [-0.0236, 37.9062], 'ethiopia': [9.145, 40.4897],
    'sudan': [12.8628, 30.2176], 'venezuela': [6.4238, -66.5897], 'colombia': [4.5709, -74.2973],
    'peru': [-9.19, -75.0152], 'chile': [-35.6751, -71.543], 'cuba': [21.5218, -77.7812],
    // Cities
    'washington': [38.9072, -77.0369], 'new york': [40.7128, -74.006], 'beijing': [39.9042, 116.4074],
    'moscow': [55.7558, 37.6173], 'london': [51.5074, -0.1278], 'paris': [48.8566, 2.3522],
    'berlin': [52.52, 13.405], 'tokyo': [35.6762, 139.6503], 'seoul': [37.5665, 126.978],
    'taipei': [25.033, 121.5654], 'hong kong': [22.3193, 114.1694], 'shanghai': [31.2304, 121.4737],
    'silicon valley': [37.3875, -122.0575], 'san francisco': [37.7749, -122.4194],
    'brussels': [50.8503, 4.3517], 'geneva': [46.2044, 6.1432], 'zurich': [47.3769, 8.5417],
    'dubai': [25.2048, 55.2708], 'tel aviv': [32.0853, 34.7818], 'jerusalem': [31.7683, 35.2137],
    'tehran': [35.6892, 51.389], 'riyadh': [24.7136, 46.6753], 'cairo': [30.0444, 31.2357],
    'kyiv': [50.4501, 30.5234], 'kiev': [50.4501, 30.5234], 'crimea': [44.9521, 34.1024],
    'donbas': [48.0159, 37.8028], 'kharkiv': [49.9935, 36.2304], 'odessa': [46.4825, 30.7233],
    'pentagon': [38.8719, -77.0563], 'kremlin': [55.752, 37.6175], 'white house': [38.8977, -77.0365],
    'wall street': [40.7074, -74.0113], 'davos': [46.8027, 9.836]
};

// Category colors matching your CSS variables
const CATEGORY_COLORS = {
    'geopolitical': '#ff4444',
    'ai-ml': '#00ff88',
    'deep-tech': '#00aaff',
    'crypto-finance': '#ffaa00',
    'narrative': '#aa66ff',
    'breaking': '#ff4444'
};

class SigintMap {
    constructor() {
        this.map = null;
        this.markers = [];
        this.markerLayer = null;
        this.isCollapsed = false;
    }

    init() {
        // Initialize map
        this.map = L.map('sigint-map', {
            center: [30, 0],
            zoom: 2,
            minZoom: 2,
            maxZoom: 10,
            zoomControl: false,
            attributionControl: false
        });

        // CartoDB Dark tiles
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            subdomains: 'abcd',
            maxZoom: 19
        }).addTo(this.map);

        // Add zoom control to top-right
        L.control.zoom({ position: 'topright' }).addTo(this.map);

        // Marker cluster layer
        this.markerLayer = L.layerGroup().addTo(this.map);

        // Toggle button
        document.getElementById('map-toggle').addEventListener('click', () => this.toggle());

        console.log('[SIGINT] Map initialized');
    }

    toggle() {
        const container = document.getElementById('map-container');
        const toggleBtn = document.getElementById('map-toggle');
        this.isCollapsed = !this.isCollapsed;
        
        container.classList.toggle('collapsed', this.isCollapsed);
        toggleBtn.textContent = this.isCollapsed ? '▼ EXPAND MAP' : '▲ COLLAPSE MAP';
        
        if (!this.isCollapsed) {
            setTimeout(() => this.map.invalidateSize(), 300);
        }
    }

    extractLocation(text) {
        if (!text) return null;
        const lower = text.toLowerCase();
        
        // Check each location (longer names first to match "south korea" before "korea")
        const sortedLocations = Object.entries(LOCATIONS)
            .sort((a, b) => b[0].length - a[0].length);
        
        for (const [name, coords] of sortedLocations) {
            if (lower.includes(name)) {
                return { name, coords };
            }
        }
        return null;
    }

    createMarker(item, category) {
        const location = this.extractLocation(item.title + ' ' + (item.summary || ''));
        if (!location) return null;

        const color = CATEGORY_COLORS[category] || '#888';
        
        // Custom marker icon
        const icon = L.divIcon({
            className: 'sigint-marker',
            html: `<div class="marker-dot" style="background:${color};box-shadow:0 0 10px ${color}"></div>`,
            iconSize: [12, 12],
            iconAnchor: [6, 6]
        });

        const marker = L.marker(location.coords, { icon });
        
        // Popup content
        const popup = `
            <div class="map-popup">
                <div class="popup-category" style="color:${color}">${category.toUpperCase()}</div>
                <div class="popup-title">${item.title}</div>
                <div class="popup-location">📍 ${location.name.charAt(0).toUpperCase() + location.name.slice(1)}</div>
                ${item.url ? `<a href="${item.url}" target="_blank" class="popup-link">Read more →</a>` : ''}
            </div>
        `;
        
        marker.bindPopup(popup, {
            className: 'sigint-popup',
            maxWidth: 300
        });

        return marker;
    }

    updateMarkers(categoriesData) {
        // Clear existing markers
        this.markerLayer.clearLayers();
        this.markers = [];

        // Add markers for each category
        for (const [category, data] of Object.entries(categoriesData)) {
            if (!data || !data.items) continue;
            
            for (const item of data.items) {
                const marker = this.createMarker(item, category);
                if (marker) {
                    this.markers.push(marker);
                    this.markerLayer.addLayer(marker);
                }
            }
        }

        // Update counter
        const counter = document.getElementById('map-counter');
        if (counter) {
            counter.textContent = `${this.markers.length} LOCATIONS`;
        }

        console.log(`[SIGINT] Map updated with ${this.markers.length} markers`);
    }
}

// Export for use in app.js
window.SigintMap = SigintMap;
