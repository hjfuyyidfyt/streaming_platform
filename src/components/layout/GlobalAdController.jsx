import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

const GlobalAdController = () => {
    const { isAdmin } = useAuth();
    const location = useLocation();

    const shouldHideAds = isAdmin || location.pathname.startsWith('/admin');

    // Smartlink URL provided by user
    const AD_URL = "https://www.effectivegatecpm.com/ieyn4dw3fw?key=390a194dfdfcc7ab638a23fab9da0fa2";
    const COOLDOWN = 60000; // 1 minute in milliseconds

    useEffect(() => {
        if (shouldHideAds) return;

        const handleClick = (e) => {
            // Check if we verify ad triggers
            const lastTime = localStorage.getItem('lastAdTime');
            const now = Date.now();

            // If no previous trigger or cooldown passed
            if (!lastTime || (now - parseInt(lastTime)) > COOLDOWN) {
                // Open Ad
                window.open(AD_URL, '_blank');

                // Update timestamp
                localStorage.setItem('lastAdTime', now.toString());

                // Note: We do NOT prevent default here. 
                // The user wants "any click" to trigger it, but the original action should likely still happen
                // or the user accepts the interference. 
                // Popunders usually work best if they just open in background (if browser allows) 
                // or new tab without stopping the nav.
            }
        };

        // Capture phase to ensure we catch it before other handlers if needed, 
        // but bubbling (default) is safer for not breaking UI.
        // User asked "click korle ad e click lage" -> implied interception. 
        // Using capture: true makes sure we run before React synthetic events? 
        // Actually document level click works fine.
        window.addEventListener('click', handleClick);

        return () => {
            window.removeEventListener('click', handleClick);
        };
    }, []);

    return null; // Logic only component
};

export default GlobalAdController;
