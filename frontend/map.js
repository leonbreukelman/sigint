/**
 * SIGINT Dashboard - World Map Module
 * Leaflet integration with CartoDB Dark tiles
 */

const SigintMap = (function() {
    'use strict';

    // Map instance and layers
    let map = null;
    let markersLayer = null;
    let isCollapsed = false;

    // Category colors matching CSS variables
    const CATEGORY_COLORS = {
        'geopolitical': '#ff4444',
        'ai-ml': '#00aaff',
        'deep-tech': '#aa66ff',
        'crypto-finance': '#ffaa00',
        'narrative': '#00ff88',
        'breaking': '#ff4444'
    };

    const CATEGORY_CLASSES = {
        'geopolitical': 'geo',
        'ai-ml': 'ai',
        'deep-tech': 'tech',
        'crypto-finance': 'crypto',
        'narrative': 'narrative',
        'breaking': 'geo'
    };

    // Expanded location database with coordinates
    // Format: { keyword: [lat, lng], ... }
    const LOCATIONS = {
        // Major Countries
        'united states': [39.8283, -98.5795], 'usa': [39.8283, -98.5795], 'u.s.': [39.8283, -98.5795], 'america': [39.8283, -98.5795], 'american': [39.8283, -98.5795],
        'china': [35.8617, 104.1954], 'chinese': [35.8617, 104.1954], 'beijing': [39.9042, 116.4074], 'shanghai': [31.2304, 121.4737],
        'russia': [61.5240, 105.3188], 'russian': [61.5240, 105.3188], 'moscow': [55.7558, 37.6173], 'kremlin': [55.7520, 37.6175],
        'ukraine': [48.3794, 31.1656], 'ukrainian': [48.3794, 31.1656], 'kyiv': [50.4501, 30.5234], 'kiev': [50.4501, 30.5234],
        'india': [20.5937, 78.9629], 'indian': [20.5937, 78.9629], 'new delhi': [28.6139, 77.2090], 'mumbai': [19.0760, 72.8777],
        'japan': [36.2048, 138.2529], 'japanese': [36.2048, 138.2529], 'tokyo': [35.6762, 139.6503],
        'germany': [51.1657, 10.4515], 'german': [51.1657, 10.4515], 'berlin': [52.5200, 13.4050],
        'france': [46.2276, 2.2137], 'french': [46.2276, 2.2137], 'paris': [48.8566, 2.3522],
        'uk': [55.3781, -3.4360], 'britain': [55.3781, -3.4360], 'british': [55.3781, -3.4360], 'london': [51.5074, -0.1278], 'england': [52.3555, -1.1743],
        'canada': [56.1304, -106.3468], 'canadian': [56.1304, -106.3468], 'toronto': [43.6532, -79.3832], 'ottawa': [45.4215, -75.6972],
        'australia': [-25.2744, 133.7751], 'australian': [-25.2744, 133.7751], 'sydney': [-33.8688, 151.2093],
        'brazil': [-14.2350, -51.9253], 'brazilian': [-14.2350, -51.9253], 'sao paulo': [-23.5505, -46.6333],
        'mexico': [23.6345, -102.5528], 'mexican': [23.6345, -102.5528],
        'south korea': [35.9078, 127.7669], 'korean': [35.9078, 127.7669], 'seoul': [37.5665, 126.9780],
        'north korea': [40.3399, 127.5101], 'pyongyang': [39.0392, 125.7625],
        'iran': [32.4279, 53.6880], 'iranian': [32.4279, 53.6880], 'tehran': [35.6892, 51.3890],
        'israel': [31.0461, 34.8516], 'israeli': [31.0461, 34.8516], 'tel aviv': [32.0853, 34.7818], 'jerusalem': [31.7683, 35.2137],
        'palestine': [31.9522, 35.2332], 'palestinian': [31.9522, 35.2332], 'gaza': [31.3547, 34.3088], 'west bank': [31.9466, 35.3027],
        'saudi arabia': [23.8859, 45.0792], 'saudi': [23.8859, 45.0792], 'riyadh': [24.7136, 46.6753],
        'uae': [23.4241, 53.8478], 'dubai': [25.2048, 55.2708], 'abu dhabi': [24.4539, 54.3773],
        'taiwan': [23.6978, 120.9605], 'taiwanese': [23.6978, 120.9605], 'taipei': [25.0330, 121.5654],
        'singapore': [1.3521, 103.8198],
        'hong kong': [22.3193, 114.1694],
        'vietnam': [14.0583, 108.2772], 'vietnamese': [14.0583, 108.2772], 'hanoi': [21.0278, 105.8342],
        'indonesia': [-0.7893, 113.9213], 'indonesian': [-0.7893, 113.9213], 'jakarta': [-6.2088, 106.8456],
        'philippines': [12.8797, 121.7740], 'philippine': [12.8797, 121.7740], 'manila': [14.5995, 120.9842],
        'thailand': [15.8700, 100.9925], 'thai': [15.8700, 100.9925], 'bangkok': [13.7563, 100.5018],
        'malaysia': [4.2105, 101.9758], 'malaysian': [4.2105, 101.9758],
        'pakistan': [30.3753, 69.3451], 'pakistani': [30.3753, 69.3451],
        'afghanistan': [33.9391, 67.7100], 'afghan': [33.9391, 67.7100], 'kabul': [34.5553, 69.2075],
        'iraq': [33.2232, 43.6793], 'iraqi': [33.2232, 43.6793], 'baghdad': [33.3152, 44.3661],
        'syria': [34.8021, 38.9968], 'syrian': [34.8021, 38.9968], 'damascus': [33.5138, 36.2765],
        'turkey': [38.9637, 35.2433], 'turkish': [38.9637, 35.2433], 'ankara': [39.9334, 32.8597], 'istanbul': [41.0082, 28.9784],
        'egypt': [26.8206, 30.8025], 'egyptian': [26.8206, 30.8025], 'cairo': [30.0444, 31.2357],
        'south africa': [-30.5595, 22.9375], 'african': [-30.5595, 22.9375], 'johannesburg': [-26.2041, 28.0473],
        'nigeria': [9.0820, 8.6753], 'nigerian': [9.0820, 8.6753],
        'kenya': [-0.0236, 37.9062], 'kenyan': [-0.0236, 37.9062], 'nairobi': [-1.2921, 36.8219],
        'ethiopia': [9.1450, 40.4897], 'ethiopian': [9.1450, 40.4897],
        'poland': [51.9194, 19.1451], 'polish': [51.9194, 19.1451], 'warsaw': [52.2297, 21.0122],
        'netherlands': [52.1326, 5.2913], 'dutch': [52.1326, 5.2913], 'amsterdam': [52.3676, 4.9041],
        'belgium': [50.5039, 4.4699], 'belgian': [50.5039, 4.4699], 'brussels': [50.8503, 4.3517],
        'switzerland': [46.8182, 8.2275], 'swiss': [46.8182, 8.2275], 'zurich': [47.3769, 8.5417], 'geneva': [46.2044, 6.1432],
        'austria': [47.5162, 14.5501], 'austrian': [47.5162, 14.5501], 'vienna': [48.2082, 16.3738],
        'sweden': [60.1282, 18.6435], 'swedish': [60.1282, 18.6435], 'stockholm': [59.3293, 18.0686],
        'norway': [60.4720, 8.4689], 'norwegian': [60.4720, 8.4689], 'oslo': [59.9139, 10.7522],
        'finland': [61.9241, 25.7482], 'finnish': [61.9241, 25.7482], 'helsinki': [60.1699, 24.9384],
        'denmark': [56.2639, 9.5018], 'danish': [56.2639, 9.5018], 'copenhagen': [55.6761, 12.5683],
        'spain': [40.4637, -3.7492], 'spanish': [40.4637, -3.7492], 'madrid': [40.4168, -3.7038], 'barcelona': [41.3851, 2.1734],
        'portugal': [39.3999, -8.2245], 'portuguese': [39.3999, -8.2245], 'lisbon': [38.7223, -9.1393],
        'italy': [41.8719, 12.5674], 'italian': [41.8719, 12.5674], 'rome': [41.9028, 12.4964], 'milan': [45.4642, 9.1900],
        'greece': [39.0742, 21.8243], 'greek': [39.0742, 21.8243], 'athens': [37.9838, 23.7275],
        'argentina': [-38.4161, -63.6167], 'argentinian': [-38.4161, -63.6167], 'buenos aires': [-34.6037, -58.3816],
        'chile': [-35.6751, -71.5430], 'chilean': [-35.6751, -71.5430], 'santiago': [-33.4489, -70.6693],
        'colombia': [4.5709, -74.2973], 'colombian': [4.5709, -74.2973],
        'venezuela': [6.4238, -66.5897], 'venezuelan': [6.4238, -66.5897],
        'peru': [-9.1900, -75.0152], 'peruvian': [-9.1900, -75.0152],
        'new zealand': [-40.9006, 174.8860], 'auckland': [-36.8509, 174.7645],
        
        // US Cities
        'washington': [38.9072, -77.0369], 'washington dc': [38.9072, -77.0369], 'white house': [38.8977, -77.0365], 'pentagon': [38.8719, -77.0563], 'capitol': [38.8899, -77.0091],
        'new york': [40.7128, -74.0060], 'nyc': [40.7128, -74.0060], 'wall street': [40.7060, -74.0088], 'manhattan': [40.7831, -73.9712],
        'san francisco': [37.7749, -122.4194], 'silicon valley': [37.3875, -122.0575], 'bay area': [37.7749, -122.4194],
        'los angeles': [34.0522, -118.2437], 'la': [34.0522, -118.2437], 'hollywood': [34.0928, -118.3287],
        'seattle': [47.6062, -122.3321],
        'boston': [42.3601, -71.0589],
        'chicago': [41.8781, -87.6298],
        'austin': [30.2672, -97.7431],
        'denver': [39.7392, -104.9903],
        'miami': [25.7617, -80.1918],
        'atlanta': [33.7490, -84.3880],
        'houston': [29.7604, -95.3698],
        'dallas': [32.7767, -96.7970],
        'phoenix': [33.4484, -112.0740],
        'las vegas': [36.1699, -115.1398],
        
        // Regions & Geopolitical
        'europe': [54.5260, 15.2551], 'european': [54.5260, 15.2551], 'eu': [50.8503, 4.3517],
        'asia': [34.0479, 100.6197], 'asian': [34.0479, 100.6197],
        'middle east': [29.2985, 42.5510], 'mideast': [29.2985, 42.5510],
        'africa': [8.7832, 34.5085],
        'latin america': [-8.7832, -55.4915],
        'nato': [50.8796, 4.4379],
        'arctic': [71.7069, -42.6043],
        'antarctic': [-82.8628, 135.0000], 'antarctica': [-82.8628, 135.0000],
        'pacific': [0, -160], 'indo-pacific': [0, 120],
        'baltic': [58.5953, 25.0136],
        'mediterranean': [35.5, 18.0],
        'south china sea': [12.0, 114.0],
        'taiwan strait': [24.5, 119.5],
        'crimea': [45.3453, 34.4997],
        'donbas': [48.0159, 37.8028],
        
        // Tech/Business Hubs
        'shenzhen': [22.5431, 114.0579],
        'bangalore': [12.9716, 77.5946], 'bengaluru': [12.9716, 77.5946],
        'tel aviv': [32.0853, 34.7818],
        'amsterdam': [52.3676, 4.9041],
        'dublin': [53.3498, -6.2603],
        
        // Organizations/Entities (headquarters)
        'openai': [37.7749, -122.4194],
        'google': [37.4220, -122.0841],
        'apple': [37.3346, -122.0090],
        'microsoft': [47.6740, -122.1215],
        'amazon': [47.6062, -122.3321],
        'meta': [37.4845, -122.1477],
        'nvidia': [37.3707, -122.0375],
        'tesla': [30.2231, -97.6226],
        'spacex': [25.9975, -97.1569],
        'anthropic': [37.7749, -122.4194],
        'deepmind': [51.5313, -0.1258],
        'baidu': [39.9847, 116.3073],
        'alibaba': [30.2741, 120.1551],
        'tencent': [22.5431, 114.0579],
        'huawei': [22.5431, 114.0579],
        'samsung': [37.5665, 126.9780],
        'tsmc': [24.7737, 121.0158]
    };

    /**
     * Extract location from text using keyword matching
     */
    function extractLocation(text) {
        if (!text) return null;
        
        const lowerText = text.toLowerCase();
        
        // Sort locations by specificity (longer names first)
        const sortedLocations = Object.keys(LOCATIONS).sort((a, b) => b.length - a.length);
        
        for (const keyword of sortedLocations) {
            // Use word boundary matching for better accuracy
            const regex = new RegExp(`\\b${keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i');
            if (regex.test(lowerText)) {
                return {
                    name: keyword.charAt(0).toUpperCase() + keyword.slice(1),
                    coords: LOCATIONS[keyword]
                };
            }
        }
        
        return null;
    }

    /**
     * Create custom marker icon
     */
    function createMarkerIcon(category, isRecent = false) {
        const className = CATEGORY_CLASSES[category] || 'geo';
        const recentClass = isRecent ? ' recent' : '';
        
        return L.divIcon({
            className: 'sigint-marker-wrapper',
            html: `<div class="sigint-marker ${className}${recentClass}"></div>`,
            iconSize: [24, 24],
            iconAnchor: [12, 12],
            popupAnchor: [0, -12]
        });
    }

    /**
     * Create popup content for a news item
     */
    function createPopupContent(item, category, locationName) {
        const categoryClass = CATEGORY_CLASSES[category] || 'geo';
        const categoryLabel = category.replace('-', '/').toUpperCase();
        const timeAgo = formatRelativeTime(item.published_at || item.fetched_at);
        
        return `
            <div class="map-popup">
                <div class="map-popup-category ${categoryClass}">
                    📍 ${locationName} • ${categoryLabel}
                </div>
                <div class="map-popup-title">
                    ${item.url ? `<a href="${item.url}" target="_blank" rel="noopener">${item.title}</a>` : item.title}
                </div>
                <div class="map-popup-meta">
                    <span class="map-popup-source">${item.source || 'Unknown'}</span>
                    <span>${timeAgo}</span>
                </div>
            </div>
        `;
    }

    /**
     * Check if item was published recently (within 1 hour)
     */
    function isRecent(item) {
        if (!item.published_at && !item.fetched_at) return false;
        const itemDate = new Date(item.published_at || item.fetched_at);
        const hourAgo = new Date(Date.now() - 60 * 60 * 1000);
        return itemDate > hourAgo;
    }

    /**
     * Format relative time (matching app.js)
     */
    function formatRelativeTime(date) {
        if (!date) return '';
        const now = new Date();
        const d = new Date(date);
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMs / 3600000);
        
        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        return d.toLocaleDateString();
    }

    /**
     * Initialize the map
     */
    function init() {
        if (map) return; // Already initialized
        
        const mapElement = document.getElementById('worldMap');
        if (!mapElement) return;

        // Create map centered on Atlantic (shows both Americas and Europe)
        map = L.map('worldMap', {
            center: [30, 0],
            zoom: 2,
            minZoom: 2,
            maxZoom: 10,
            zoomControl: true,
            attributionControl: true
        });

        // Add CartoDB Dark tiles
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 19
        }).addTo(map);

        // Create marker cluster group
        markersLayer = L.markerClusterGroup({
            maxClusterRadius: 50,
            spiderfyOnMaxZoom: true,
            showCoverageOnHover: false,
            zoomToBoundsOnClick: true,
            disableClusteringAtZoom: 5
        });
        
        map.addLayer(markersLayer);

        // Setup toggle functionality
        setupToggle();

        console.log('[SIGINT] Map initialized');
    }

    /**
     * Setup map collapse/expand toggle
     */
    function setupToggle() {
        const header = document.getElementById('mapHeader');
        const section = document.getElementById('mapSection');
        
        if (header && section) {
            header.addEventListener('click', () => {
                isCollapsed = !isCollapsed;
                section.classList.toggle('collapsed', isCollapsed);
                
                // Invalidate map size after animation completes
                if (!isCollapsed) {
                    setTimeout(() => {
                        map.invalidateSize();
                    }, 350);
                }
            });
        }
    }

    /**
     * Update map with news items from all categories
     */
    function update(categoriesData) {
        if (!map || !markersLayer) {
            init();
            if (!map) return;
        }

        // Clear existing markers
        markersLayer.clearLayers();
        
        let totalEvents = 0;
        const processedLocations = new Set(); // Avoid duplicate markers for same location

        // Process each category
        for (const [category, data] of Object.entries(categoriesData)) {
            if (!data || !data.items || category === 'markets') continue;
            
            for (const item of data.items) {
                // Try to extract location from title first, then summary
                let location = extractLocation(item.title);
                if (!location && item.summary) {
                    location = extractLocation(item.summary);
                }
                
                if (location) {
                    // Create unique key to avoid exact duplicates
                    const locKey = `${location.coords[0]},${location.coords[1]},${category}`;
                    
                    // Add small random offset if location already used (to prevent exact overlap)
                    let coords = location.coords;
                    if (processedLocations.has(locKey)) {
                        coords = [
                            location.coords[0] + (Math.random() - 0.5) * 0.5,
                            location.coords[1] + (Math.random() - 0.5) * 0.5
                        ];
                    }
                    processedLocations.add(locKey);
                    
                    // Create marker
                    const marker = L.marker(coords, {
                        icon: createMarkerIcon(category, isRecent(item))
                    });
                    
                    // Add popup
                    marker.bindPopup(createPopupContent(item, category, location.name), {
                        maxWidth: 300,
                        className: 'sigint-popup'
                    });
                    
                    markersLayer.addLayer(marker);
                    totalEvents++;
                }
            }
        }

        // Update stats
        const statsElement = document.getElementById('mapStats');
        if (statsElement) {
            statsElement.textContent = `${totalEvents} event${totalEvents !== 1 ? 's' : ''} mapped`;
        }

        console.log(`[SIGINT] Map updated with ${totalEvents} events`);
    }

    /**
     * Fit map bounds to show all markers
     */
    function fitBounds() {
        if (map && markersLayer && markersLayer.getLayers().length > 0) {
            map.fitBounds(markersLayer.getBounds(), {
                padding: [20, 20],
                maxZoom: 5
            });
        }
    }

    /**
     * Public API
     */
    return {
        init: init,
        update: update,
        fitBounds: fitBounds,
        extractLocation: extractLocation // Expose for testing
    };
})();

// Initialize map when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', SigintMap.init);
} else {
    SigintMap.init();
}
