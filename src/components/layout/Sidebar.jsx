import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext.jsx';
import {
    Home,
    Compass,
    PlaySquare,
    Clock,
    ThumbsUp,
    ListVideo,
    History,
    Flame,
    Music,
    Gamepad2,
    Trophy,
    Film,
    Radio,
    Settings,
    HelpCircle,
    Flag,
    ChevronRight,
    Video,
    User
} from 'lucide-react';

// Helper components
const NavItem = ({ icon: IconComponent, label, path, isActive }) => (
    <Link
        to={path}
        className={`flex items-center gap-5 px-3 py-2.5 rounded-lg transition-all group ${isActive
            ? 'bg-white/10 font-medium'
            : 'hover:bg-white/5'
            }`}
    >
        <IconComponent className={`w-5 h-5 ${isActive ? 'text-white' : 'text-gray-400 group-hover:text-white'}`} />
        <span className={`text-sm ${isActive ? 'text-white' : 'text-gray-300 group-hover:text-white'}`}>
            {label}
        </span>
    </Link>
);

const SectionHeader = ({ title, showArrow = false }) => (
    <div className="flex items-center justify-between px-3 pt-4 pb-1">
        <h3 className="text-sm font-medium text-gray-300">{title}</h3>
        {showArrow && <ChevronRight className="w-4 h-4 text-gray-500" />}
    </div>
);

const Divider = () => (
    <div className="border-t border-gray-800 my-3 mx-3" />
);

const Sidebar = ({ isOpen = true, categories = [], onClose = () => { }, isOverlay = false }) => {
    const location = useLocation();
    const { isAuthenticated } = useAuth();

    const isActive = (path) => location.pathname === path;

    // Main navigation items
    const mainItems = [
        { icon: Home, label: 'Home', path: '/' },
        { icon: Compass, label: 'Explore', path: '/explore' },
        { icon: PlaySquare, label: 'Shorts', path: '/shorts' },
        { icon: Radio, label: 'Subscriptions', path: '/subscriptions' },
    ];

    // "You" section items - requires auth
    const youItems = [
        { icon: Video, label: 'Your videos', path: '/your-videos' },
        { icon: History, label: 'History', path: '/history' },
        { icon: ListVideo, label: 'Playlists', path: '/playlists' },
        { icon: Clock, label: 'Watch later', path: '/watch-later' },
        { icon: ThumbsUp, label: 'Liked videos', path: '/liked' },
    ];

    // Explore section
    const exploreItems = [
        { icon: Flame, label: 'Trending', path: '/trending' },
        { icon: Music, label: 'Music', path: '/category/music' },
        { icon: Gamepad2, label: 'Gaming', path: '/category/gaming' },
        { icon: Trophy, label: 'Sports', path: '/category/sports' },
        { icon: Film, label: 'Movies', path: '/category/movies' },
    ];

    // Bottom items
    const bottomItems = [
        { icon: Settings, label: 'Settings', path: '/settings' },
        { icon: Flag, label: 'Report history', path: '/report-history' },
        { icon: HelpCircle, label: 'Help', path: '/help' },
    ];

    if (!isOpen && !isOverlay) {
        // Collapsed mini sidebar (Desktop only)
        return (
            <aside className="hidden lg:flex flex-col items-center w-[72px] h-[calc(100vh-56px)] overflow-y-auto fixed top-14 left-0 z-40 bg-[#0f0f0f] py-3">
                {mainItems.slice(0, 4).map(item => (
                    <Link
                        key={item.path}
                        to={item.path}
                        className={`flex flex-col items-center justify-center w-16 h-16 rounded-lg transition-all ${isActive(item.path) ? 'bg-white/10' : 'hover:bg-white/5'
                            }`}
                    >
                        <item.icon className={`w-5 h-5 mb-1 ${isActive(item.path) ? 'text-white' : 'text-gray-400'}`} />
                        <span className="text-[10px] text-gray-300">{item.label}</span>
                    </Link>
                ))}
            </aside>
        );
    }

    return (
        <>
            {/* Overlay backdrop */}
            <div
                className={`fixed inset-0 bg-black/50 z-40 ${isOverlay ? '' : 'lg:hidden'} ${isOpen ? 'block' : 'hidden'}`}
                onClick={onClose}
            />

            <aside className={`
                w-60 h-[calc(100vh-56px)] overflow-y-auto bg-[#0f0f0f] scrollbar-thin scrollbar-thumb-gray-700
                fixed top-14 left-0 z-50
                transition-transform duration-300 ease-in-out
                ${isOpen ? 'translate-x-0' : `-translate-x-full ${!isOverlay ? 'lg:translate-x-0 lg:w-[72px]' : ''}`} 
            `}>
                <div className="py-3 px-2">
                    <nav className="space-y-0.5">
                        {mainItems.map(item => (
                            <NavItem
                                key={item.path}
                                icon={item.icon}
                                label={item.label}
                                path={item.path}
                                isActive={isActive(item.path)}
                            />
                        ))}
                    </nav>

                    <Divider />

                    <SectionHeader title="You" showArrow />
                    <nav className="space-y-0.5">
                        {youItems.map(item => (
                            <NavItem
                                key={item.path}
                                icon={item.icon}
                                label={item.label}
                                path={item.path}
                                isActive={isActive(item.path)}
                            />
                        ))}
                    </nav>

                    {!isAuthenticated && (
                        <div className="mx-3 mt-4 p-3 border border-gray-700 rounded-lg">
                            <p className="text-sm text-gray-400 mb-3">
                                Sign in to like videos, comment, and subscribe.
                            </p>
                            <Link
                                to="/auth"
                                className="flex items-center justify-center gap-2 w-full py-2 px-4 border border-blue-500 text-blue-500 rounded-full text-sm font-medium hover:bg-blue-500/10 transition-colors"
                            >
                                <User className="w-4 h-4" />
                                Sign in
                            </Link>
                        </div>
                    )}

                    <Divider />

                    <SectionHeader title="Explore" />
                    <nav className="space-y-0.5">
                        {exploreItems.map(item => (
                            <NavItem
                                key={item.path}
                                icon={item.icon}
                                label={item.label}
                                path={item.path}
                                isActive={isActive(item.path)}
                            />
                        ))}
                    </nav>

                    {categories.length > 0 && (
                        <>
                            <Divider />
                            <SectionHeader title="Categories" />
                            <nav className="space-y-0.5">
                                {categories.filter(c => c.slug !== 'all').slice(0, 8).map(cat => (
                                    <Link
                                        key={cat.slug}
                                        to={`/category/${cat.slug}`}
                                        className={`flex items-center gap-5 px-3 py-2.5 rounded-lg transition-all group ${location.pathname === `/category/${cat.slug}`
                                            ? 'bg-white/10 font-medium'
                                            : 'hover:bg-white/5'
                                            }`}
                                    >
                                        <span className="text-sm text-gray-300 group-hover:text-white">{cat.name}</span>
                                    </Link>
                                ))}
                            </nav>
                        </>
                    )}

                    <Divider />

                    <nav className="space-y-0.5">
                        {bottomItems.map(item => (
                            <NavItem
                                key={item.path}
                                icon={item.icon}
                                label={item.label}
                                path={item.path}
                                isActive={isActive(item.path)}
                            />
                        ))}
                    </nav>

                    <div className="mt-4 px-3 pb-6">
                        <div className="text-xs text-gray-500 space-y-2">
                            <div className="flex flex-wrap gap-x-2 gap-y-1">
                                <a href="#" className="hover:text-gray-300">About</a>
                                <a href="#" className="hover:text-gray-300">Press</a>
                                <a href="#" className="hover:text-gray-300">Copyright</a>
                            </div>
                            <div className="flex flex-wrap gap-x-2 gap-y-1">
                                <a href="#" className="hover:text-gray-300">Contact us</a>
                                <a href="#" className="hover:text-gray-300">Creators</a>
                            </div>
                            <div className="flex flex-wrap gap-x-2 gap-y-1">
                                <a href="#" className="hover:text-gray-300">Terms</a>
                                <a href="#" className="hover:text-gray-300">Privacy</a>
                                <a href="#" className="hover:text-gray-300">Policy & Safety</a>
                            </div>
                            <p className="pt-3 text-gray-600">© 2026 StreamPlatform</p>
                        </div>
                    </div>
                </div>
            </aside>
        </>
    );
};

export default Sidebar;
