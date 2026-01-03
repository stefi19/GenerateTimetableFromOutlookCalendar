import React from 'react'

export default function RouteMap() {
  return (
    <div className="route-map-container">
      <h2>Cluj Route Map</h2>
      <svg 
        id="Cluj-Route-TLights" 
        width="100%" 
        height="600" 
        viewBox="0 0 1440 900" 
        xmlns="http://www.w3.org/2000/svg"
        style={{ maxWidth: '100%', height: 'auto' }}
      >
        <defs>
          <linearGradient id="bgBlue4" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#0EA5FF"/>
            <stop offset="100%" stopColor="#3B82F6"/>
          </linearGradient>
          <filter id="soft3" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="6"/>
          </filter>
          <path id="RoutePath15" d="M200 820 C 320 740, 420 680, 520 640 S 740 580, 820 560 S 960 520, 1040 480"/>
          <style>{`
            .ui { font-family: 'Inter', Arial, sans-serif; }
            .grid { stroke:#E2EEFC; stroke-width:12; stroke-linecap:round; fill:none; }
            .minor { stroke:#CCE1FB; stroke-width:8; stroke-linecap:round; fill:none; }
            .primary { stroke:#1D4ED8; stroke-width:16; opacity:.22; fill:none; }
            .route { stroke:#60A5FA; stroke-width:10; stroke-linecap:round; fill:none; stroke-dasharray:18 12; }
            .poi { fill:#FFFFFF; stroke:#93C5FD; stroke-width:2; }
            .poi-label { font-size:18px; fill:#1E3A8A; }
            .chip { fill:#1D4ED8; }
            .chip-txt { fill:#DBEAFE; font-size:18px; }
          `}</style>
        </defs>

        {/* Background */}
        <rect width="1440" height="900" fill="url(#bgBlue4)"/>
        <rect x="24" y="24" width="1392" height="852" rx="28" fill="#EFF6FF" opacity="0.85"/>

        {/* Streets */}
        <g className="ui">
          <path className="grid" d="M160 120 L420 160 L760 140 L1120 180"/>
          <path className="grid" d="M120 320 L480 300 L780 380 L1100 360 L1300 420"/>
          <path className="grid" d="M140 500 L520 460 L900 500 L1220 540"/>
          <path className="grid" d="M220 680 L520 640 L920 660 L1230 680"/>
          <path className="minor" d="M340 160 L320 360 L360 560 L380 760"/>
          <path className="minor" d="M700 140 L720 320 L740 520 L760 740"/>
          <path className="minor" d="M1040 180 L1020 360 L1030 560 L1040 760"/>
        </g>

        {/* E81 subtle */}
        <path className="primary" d="M90 280 L460 260 L780 320 L1180 300"/>
        <text x="740" y="272" className="ui" style={{ fontSize: '20px', fill: '#1E40AF', opacity: 0.5 }}>E81</text>

        {/* Active route */}
        <path id="ActiveRoute15" className="route" d="M200 820 C 320 740, 420 680, 520 640 S 740 580, 820 560 S 960 520, 1040 480">
          <animate attributeName="stroke-dashoffset" from="0" to="-300" dur="12s" repeatCount="indefinite"/>
        </path>

        {/* POIs */}
        <g id="POIs15" className="ui">
          <g transform="translate(200,820)">
            <circle r="10" className="poi"/>
            <text x="12" y="6" className="poi-label">Heart Institute</text>
          </g>
          <g transform="translate(600,620)">
            <circle r="10" className="poi"/>
            <text x="12" y="6" className="poi-label">Unirii Square</text>
          </g>
          <g transform="translate(820,560)">
            <circle r="10" className="poi"/>
            <text x="12" y="6" className="poi-label">Babeș-Bolyai University</text>
          </g>
          <g transform="translate(1040,480)">
            <circle r="10" className="poi"/>
            <text x="12" y="6" className="poi-label">Tailors' Bastion</text>
          </g>
        </g>

        {/* Traffic Lights */}
        <g id="TL-Unirii" transform="translate(540,640)">
          <rect x="-10" y="-26" width="20" height="52" rx="4" fill="#0f172a" opacity=".85"/>
          <circle cx="0" cy="-14" r="6" fill="#ef4444">
            <animate attributeName="opacity" values="1;0.25;1" dur="4s" repeatCount="indefinite"/>
          </circle>
          <circle cx="0" cy="0" r="6" fill="#fbbf24" opacity=".25"/>
          <circle cx="0" cy="14" r="6" fill="#22c55e">
            <animate attributeName="opacity" values="0.25;1;0.25" dur="4s" repeatCount="indefinite"/>
          </circle>
        </g>

        <g id="TL-UBB" transform="translate(780,560)">
          <rect x="-10" y="-26" width="20" height="52" rx="4" fill="#0f172a" opacity=".85"/>
          <circle cx="0" cy="-14" r="6" fill="#ef4444">
            <animate attributeName="opacity" values="1;0.25;1" dur="4s" begin="1.3s" repeatCount="indefinite"/>
          </circle>
          <circle cx="0" cy="0" r="6" fill="#fbbf24" opacity=".25"/>
          <circle cx="0" cy="14" r="6" fill="#22c55e">
            <animate attributeName="opacity" values="0.25;1;0.25" dur="4s" begin="1.3s" repeatCount="indefinite"/>
          </circle>
        </g>

        <g id="TL-Bastion" transform="translate(1000,500)">
          <rect x="-10" y="-26" width="20" height="52" rx="4" fill="#0f172a" opacity=".85"/>
          <circle cx="0" cy="-14" r="6" fill="#ef4444">
            <animate attributeName="opacity" values="1;0.25;1" dur="4s" begin="2.6s" repeatCount="indefinite"/>
          </circle>
          <circle cx="0" cy="0" r="6" fill="#fbbf24" opacity=".25"/>
          <circle cx="0" cy="14" r="6" fill="#22c55e">
            <animate attributeName="opacity" values="0.25;1;0.25" dur="4s" begin="2.6s" repeatCount="indefinite"/>
          </circle>
        </g>

        {/* Ambulance */}
        <g id="Ambulance15">
          <g id="AmbBody15">
            <rect x="-28" y="-16" width="64" height="32" rx="6" fill="#FFFFFF" stroke="#1D4ED8" strokeWidth="2"/>
            <rect x="10" y="-26" width="26" height="18" rx="4" fill="#DBEAFE" stroke="#1D4ED8" strokeWidth="2"/>
            <circle cx="-10" cy="20" r="9" fill="#1E3A8A"/>
            <circle cx="22" cy="20" r="9" fill="#1E3A8A"/>
            <rect x="-4" y="-10" width="18" height="6" fill="#EF4444"/>
            <path d="M-1 -7 h4 v-4 h6 v4 h4 v6 h-4 v4 h-6 v-4 h-4z" fill="#FFFFFF"/>
          </g>
          <animateMotion dur="12s" repeatCount="indefinite" rotate="auto">
            <mpath xlinkHref="#ActiveRoute15"/>
          </animateMotion>
        </g>

        {/* Info chip */}
        <g transform="translate(40,40)">
          <rect width="380" height="84" rx="18" className="chip"/>
          <text x="20" y="34" className="ui" style={{ fontSize: '22px', fill: '#FFFFFF' }}>Ambulance #A2</text>
          <text x="20" y="62" className="chip-txt">ETA 3 min • Moving to Tailors' Bastion</text>
        </g>
      </svg>

      <div className="map-legend">
        <p><strong>Heart Institute</strong> → <strong>Tailors' Bastion</strong></p>
        <p>Route through Unirii Square and Babeș-Bolyai University</p>
      </div>
    </div>
  )
}
