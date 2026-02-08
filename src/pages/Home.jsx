import React, { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import VideoCard from '../components/video/VideoCard.jsx';
import SkeletonVideoCard from '../components/video/SkeletonVideoCard.jsx';
import Sidebar from '../components/layout/Sidebar.jsx';
import { useAuth } from '../context/AuthContext.jsx';
import { Search, Menu, Bell, Upload, User } from 'lucide-react';
// import AdBanner from '../components/layout/AdBanner';

// Mock data for Phase 2 visualization
import { api } from '../services/api.js';

const Home = () => {
    const { slug } = useParams(); // Get category slug from URL
    const [videos, setVideos] = useState([]);
    const [categories, setCategories] = useState([]);
    const [continueWatching, setContinueWatching] = useState([]);
    const [activeCategory, setActiveCategory] = useState({ name: 'All', slug: 'all' });
    const [searchQuery, setSearchQuery] = useState('');
    const [isLoading, setIsLoading] = useState(true);
    // Default closed on mobile (< 1024px), open on desktop
    const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth >= 1024);
    const { user, isAuthenticated, logout } = useAuth();

    // Initial Fetch (Categories only)
    useEffect(() => {
        const fetchCategories = async () => {
            try {
                const cats = await api.getCategories();
                // Add 'All' option manually
                setCategories([{ name: "All", slug: "all" }, ...cats]);
            } catch (err) {
                console.error("Failed to load categories", err);
            }
        };

        fetchCategories();
    }, []);

    // Handle URL-based category (from /category/:slug route)
    useEffect(() => {
        if (categories.length === 0) return;

        if (slug) {
            const cat = categories.find(c => c.slug === slug);
            if (cat && cat.slug !== activeCategory.slug) {
                setActiveCategory(cat);
            }
        } else if (!slug && activeCategory.slug !== 'all') {
            setActiveCategory({ name: 'All', slug: 'all' });
        }
    }, [slug, categories, activeCategory.slug]);

    // Filter/Search Logic - Handles ALL video fetching including initial load
    useEffect(() => {
        const fetchFilteredVideos = async () => {
            setIsLoading(true);
            try {
                let data;
                if (searchQuery) {
                    data = await api.searchVideos(searchQuery);
                } else if (activeCategory.slug !== 'all') {
                    data = await api.getVideosByCategory(activeCategory.slug);
                } else {
                    data = await api.getVideos();
                }
                setVideos(data);

                if (isAuthenticated) {
                    const cwData = await api.getContinueWatching(localStorage.getItem('token'));
                    setContinueWatching(cwData.continue_watching || []);
                }
            } catch (err) {
                console.error("Filtering failed", err);
            } finally {
                setIsLoading(false);
            }
        };

        // Debounce search
        const timeoutId = setTimeout(() => {
            fetchFilteredVideos();
        }, 300);

        return () => clearTimeout(timeoutId);
    }, [searchQuery, activeCategory]);

    return (
        <div className="min-h-screen bg-[#0f0f0f] text-white overflow-x-hidden">
            {/* YouTube-style Navbar */}
            <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0f0f0f] h-14 px-4 flex items-center justify-between">
                {/* Left: Menu + Logo */}
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        className="p-2 hover:bg-white/10 rounded-full transition-colors"
                    >
                        <Menu className="w-5 h-5 text-white" />
                    </button>
                    <Link to="/" className="flex items-center gap-0.5">
                        <svg className="w-8 h-8 text-red-600" viewBox="0 0 90 20" fill="currentColor">
                            <path d="M27.973 3.123A3.5 3.5 0 0 0 25.5 2H4.5A3.5 3.5 0 0 0 1 5.5v9A3.5 3.5 0 0 0 4.5 18h21a3.5 3.5 0 0 0 3.5-3.5v-9c0-.97-.395-1.841-1.027-2.377zM12 14V6l5.5 4L12 14z" />
                        </svg>
                        <span className="text-xl font-semibold tracking-tighter hidden sm:inline">
                            Stream<span className="font-light">Platform</span>
                        </span>
                    </Link>
                </div>

                {/* Center: Search Bar */}
                <div className="flex-1 max-w-2xl mx-4 hidden md:flex items-center">
                    <div className="flex flex-1">
                        <input
                            type="text"
                            placeholder="Search"
                            className="w-full bg-[#121212] border border-gray-700 rounded-l-full py-2 pl-4 pr-4 focus:outline-none focus:border-blue-500 text-sm"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                        />
                        <button className="bg-[#222222] border border-l-0 border-gray-700 px-5 rounded-r-full hover:bg-[#333333] transition-colors">
                            <Search className="w-5 h-5 text-gray-400" />
                        </button>
                    </div>
                </div>

                {/* Right: Actions */}
                <div className="flex items-center gap-2">
                    {isAuthenticated ? (
                        <>
                            <button className="p-2 hover:bg-white/10 rounded-full transition-colors">
                                <Upload className="w-5 h-5 text-white" />
                            </button>
                            <button className="p-2 hover:bg-white/10 rounded-full transition-colors">
                                <Bell className="w-5 h-5 text-white" />
                            </button>
                            <button
                                onClick={logout}
                                className="w-8 h-8 rounded-full bg-purple-600 flex items-center justify-center text-sm font-medium"
                            >
                                {user?.display_name?.charAt(0).toUpperCase() || 'U'}
                            </button>
                        </>
                    ) : (
                        <Link
                            to="/auth"
                            className="flex items-center gap-2 py-1.5 px-3 border border-gray-600 rounded-full hover:bg-blue-500/10 hover:border-blue-500 transition-colors"
                        >
                            <User className="w-5 h-5 text-blue-500" />
                            <span className="text-sm font-medium text-blue-500">Sign in</span>
                        </Link>
                    )}
                </div>
            </nav>

            <div className="flex pt-14">
                {/* YouTube-style Sidebar */}
                <Sidebar
                    isOpen={sidebarOpen}
                    categories={categories}
                    onClose={() => setSidebarOpen(false)}
                />

                {/* Main Content */}
                <main className="flex-1 p-4 lg:p-6 min-w-0">

                    {/* Mobile Categories (Horizontal Scroll) */}
                    <div className="lg:hidden flex overflow-x-auto pb-4 gap-2 mb-4 scrollbar-hide">
                        {categories.map(cat => (
                            <button
                                key={cat.slug}
                                onClick={() => {
                                    setActiveCategory(cat);
                                    setSearchQuery('');
                                }}
                                className={`whitespace-nowrap px-4 py-1.5 rounded-full text-sm font-medium transition-colors border ${activeCategory.slug === cat.slug
                                    ? 'bg-white text-black border-white'
                                    : 'bg-[#242424] text-gray-300 border-gray-700'
                                    }`}
                            >
                                {cat.name}
                            </button>
                        ))}
                    </div>

                    {continueWatching.length > 0 && (
                        <div className="mb-8">
                            <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
                                <span className="text-red-500">▶</span> Continue Watching
                            </h2>
                            <div className="flex gap-4 overflow-x-auto pb-4 scrollbar-hide">
                                {continueWatching.map(vid => (
                                    <Link key={vid.video_id} to={`/video/${vid.video_id}`} className="min-w-[240px] w-[240px] group">
                                        <div className="relative aspect-video bg-gray-800 rounded-lg overflow-hidden mb-2">
                                            <img src={vid.thumbnail_url} alt={vid.title} className="w-full h-full object-cover" />
                                            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
                                                <div className="bg-red-600 rounded-full p-2 opacity-0 group-hover:opacity-100 transition-opacity transform scale-75 group-hover:scale-100 shadow-lg">
                                                    <svg className="w-5 h-5 text-white fill-current" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                                                </div>
                                            </div>
                                            <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-700">
                                                <div className="h-full bg-red-600" style={{ width: `${vid.progress_percent}%` }}></div>
                                            </div>
                                            <span className="absolute bottom-2 right-2 bg-black/80 text-white text-[10px] px-1 rounded">
                                                {vid.progress_seconds > 60 ? `${Math.floor(vid.progress_seconds / 60)}m left` : 'Resume'}
                                            </span>
                                        </div>
                                        <h3 className="font-semibold text-sm line-clamp-2 leading-tight group-hover:text-red-500 transition-colors">
                                            {vid.title}
                                        </h3>
                                        <p className="text-xs text-gray-500 mt-1">
                                            {vid.duration ? Math.floor((vid.duration - vid.progress_seconds) / 60) : 0} min remaining
                                        </p>
                                    </Link>
                                ))}
                            </div>
                        </div>
                    )}

                    <h2 className="text-xl font-bold mb-6">Recommended for you</h2>

                    {/* <AdBanner format="banner" /> */}

                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-y-6 sm:gap-y-8 gap-x-4 w-full max-w-[350px] mx-auto sm:max-w-none px-0 sm:px-0">
                        {isLoading
                            ? Array(8).fill(null).map((_, i) => <SkeletonVideoCard key={i} />)
                            : videos.map(video => (
                                <VideoCard key={video.id} video={video} />
                            ))
                        }
                    </div>

                    {!isLoading && (
                        <div className="mt-12 flex justify-center">
                            <button className="text-gray-400 hover:text-white text-sm font-medium border border-gray-700 hover:border-gray-500 px-6 py-2 rounded-full transition-all">
                                Load More
                            </button>
                        </div>
                    )}
                </main>
            </div>
        </div>
    );
};

export default Home;
