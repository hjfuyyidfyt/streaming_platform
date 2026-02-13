import React, { useEffect, useRef } from 'react';

const AdBanner = ({ format = "banner", className = "" }) => {
    const bannerRef = useRef(null);

    useEffect(() => {
        if (!bannerRef.current) return;

        // Native Banner Implementation
        // Only run if the container is empty or we need to re-inject
        if (format === 'banner' || format === 'square') {
            // Check if script already exists to prevent duplicates on re-render
            if (bannerRef.current.querySelector('script')) return;

            const script = document.createElement('script');
            script.async = true;
            script.dataset.cfasync = "false";
            script.src = "//pl28706593.effectivegatecpm.com/2260504880a1a301d3ee9ca7479cffa9/invoke.js";

            try {
                bannerRef.current.appendChild(script);
            } catch (e) {
                console.error("Ad script injection failed", e);
            }
        }
    }, [format]);

    // Dimensions based on format
    const getDimensions = () => {
        switch (format) {
            case 'square': return 'w-[300px] h-[250px]';
            case 'vertical': return 'w-[160px] h-[600px]';
            case 'banner':
            default: return 'w-full max-w-[728px] h-[90px]';
        }
    };

    return (
        <div className={`flex justify-center my-6 ${className}`}>
            <div
                ref={bannerRef}
                className="bg-[#242424] flex items-center justify-center overflow-hidden min-h-[90px] min-w-[300px]"
            >
                {/* Native Banner Container */}
                <div id="container-2260504880a1a301d3ee9ca7479cffa9"></div>
            </div>
        </div>
    );
};

export default AdBanner;
