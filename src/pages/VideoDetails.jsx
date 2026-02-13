import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../services/api.js';
import { useAuth } from '../context/AuthContext.jsx';
import { Share2, Eye, Calendar, Settings, User, LogOut, AlertCircle, RefreshCw, ThumbsUp, ThumbsDown, Download, MoreHorizontal, ChevronDown, ChevronUp, Search, Bell, Menu } from 'lucide-react';
import VideoCard from '../components/video/VideoCard.jsx';
import AdBanner from '../components/layout/AdBanner.jsx';
import LikeButton from '../components/video/LikeButton.jsx';
import CommentSection from '../components/video/CommentSection.jsx';
import SubscribeButton from '../components/video/SubscribeButton.jsx';
import AddToPlaylist from '../components/video/AddToPlaylist.jsx';
import Sidebar from '../components/layout/Sidebar.jsx'; // Import Sidebar
import { ListPlus } from 'lucide-react';

const VideoDetails = () => {
    const { id } = useParams();
    const { user, isAuthenticated, logout } = useAuth();
    const [video, setVideo] = useState(null);
    const [relatedVideos, setRelatedVideos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [sources, setSources] = useState([]);
    const [activeSource, setActiveSource] = useState(null);
    const [isProcessing, setIsProcessing] = useState(false);
    const [descExpanded, setDescExpanded] = useState(false);

    // Quality selection state
    const [currentResolution, setCurrentResolution] = useState(null);
    const [showQualityMenu, setShowQualityMenu] = useState(false);
    const [showPlaylistModal, setShowPlaylistModal] = useState(false);
    const [playbackError, setPlaybackError] = useState(false);
    const videoRef = useRef(null);
    const lastSavedTime = useRef(0);
    const initialSeekDone = useRef(false);
    const [adOverlayVisible, setAdOverlayVisible] = useState(true);
    const [sidebarOpen, setSidebarOpen] = useState(false); // Sidebar state
    const [categories, setCategories] = useState([]); // Categories state

    const handleAdClick = () => {
        const adUrl = "https://www.effectivegatecpm.com/ieyn4dw3fw?key=390a194dfdfcc7ab638a23fab9da0fa2";
        if (adUrl && adUrl !== "#") {
            window.open(adUrl, "_blank");
        }
        setAdOverlayVisible(false);
        if (videoRef.current) {
            videoRef.current.play().catch(err => console.error("Play failed", err));
        }
    };

    // Fetch video details and categories
    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                // Fetch video details and categories in parallel
                const [videoData, categoriesData] = await Promise.all([
                    api.getVideo(id),
                    api.getCategories()
                ]);

                setVideo(videoData);
                setCategories([{ name: "All", slug: "all" }, ...categoriesData]);

                // Fetch related videos (by category if available)
                let relatedData = [];
                if (videoData.category && videoData.category.slug) {
                    relatedData = await api.getVideosByCategory(videoData.category.slug, 0, 15);
                } else {
                    relatedData = await api.getVideos(0, 15);
                }
                setRelatedVideos(relatedData.filter(v => v.id !== parseInt(id)));

                const videoSources = videoData.sources || [];
                // ... (rest of source logic follows) ...
                if (videoSources.length === 0) {
                    if (videoData.storage_mode === 'streamtape' || videoData.storage_mode === 'doodstream') {
                        videoSources.push({
                            id: 'primary',
                            provider: videoData.storage_mode,
                            resolution: videoData.original_resolution || 'Original',
                            embed_url: videoData.embed_url
                        });
                    } else {
                        videoSources.push({
                            id: 'primary',
                            provider: 'local',
                            resolution: videoData.original_resolution || 'Original',
                            embed_url: null
                        });
                    }
                }
                setSources(videoSources);

                const priority = ['doodstream', 'telegram', 'streamtape', 'local'];
                const uniqueProviders = [...new Set(videoSources.map(s => s.provider))];
                const bestProvider = uniqueProviders.sort((a, b) => priority.indexOf(a) - priority.indexOf(b))[0];
                const providerSources = videoSources.filter(s => s.provider === bestProvider);
                const bestSource = providerSources[0];

                setActiveSource(bestSource || videoSources[0]);
                setCurrentResolution(bestSource?.resolution || 'Original');

                // Record view
                api.recordView(id);

            } catch (err) {
                console.error("Failed to fetch video data", err);
            } finally {
                setLoading(false);
            }
        };

        if (id) {
            fetchData();
            window.scrollTo(0, 0);
            setDescExpanded(false);
            setAdOverlayVisible(true);
        }
    }, [id]);

    useEffect(() => {
        if (videoRef.current) {
            videoRef.current.load();
            setPlaybackError(false);
        }
    }, [activeSource]);

    const handleReloadVideo = () => {
        if (videoRef.current) {
            setPlaybackError(false);
            videoRef.current.load();
            videoRef.current.play().catch(err => console.error("Play failed", err));
        }
    };

    useEffect(() => {
        let interval;
        const checkProcessing = (currentSources) => {
            if (!currentSources || currentSources.length === 0) return true;
            return currentSources.length < 9;
        };

        if (video && checkProcessing(sources)) {
            setIsProcessing(true);
            interval = setInterval(async () => {
                try {
                    const videoData = await api.getVideo(id);
                    const newSources = videoData.sources || [];
                    if (newSources.length !== sources.length) {
                        setSources(newSources);
                    }
                    if (!checkProcessing(newSources)) {
                        setIsProcessing(false);
                        clearInterval(interval);
                    }
                } catch (err) {
                    console.error("Polling error", err);
                }
            }, 20000);
        } else {
            setIsProcessing(false);
        }
        return () => clearInterval(interval);
    }, [id, video, sources]);

    const handleManualRefresh = async () => {
        try {
            const videoData = await api.getVideo(id);
            if (videoData.sources) {
                setSources(videoData.sources);
            }
        } catch (err) {
            console.error("Refresh failed", err);
        }
    };

    useEffect(() => {
        if (video && isAuthenticated && !initialSeekDone.current) {
            const fetchProgress = async () => {
                try {
                    const token = localStorage.getItem('token');
                    const p = await api.getVideoProgress(id, token);
                    if (p && p.progress_seconds > 0 && videoRef.current) {
                        videoRef.current.currentTime = p.progress_seconds;
                        initialSeekDone.current = true;
                    }
                } catch (e) {
                    console.error("Failed to restore progress", e);
                }
            };
            fetchProgress();
        }
    }, [video, isAuthenticated, id]);

    const handleTimeUpdate = () => {
        if (!videoRef.current || !isAuthenticated) return;
        const currentTime = Math.floor(videoRef.current.currentTime);
        if (Math.abs(currentTime - lastSavedTime.current) >= 10) {
            lastSavedTime.current = currentTime;
            const token = localStorage.getItem('token');
            const total = videoRef.current.duration;
            const completed = total > 0 && (currentTime / total) > 0.9;
            api.saveProgress(video.id, currentTime, completed, token).catch(e => console.error(e));
        }
    };

    const handleServerChange = (newProvider) => {
        const providerSources = sources.filter(s => s.provider === newProvider);
        if (providerSources.length === 0) return;
        let newSource = providerSources.find(s => s.resolution === currentResolution);
        if (!newSource) {
            newSource = providerSources[0];
        }
        setActiveSource(newSource);
        setCurrentResolution(newSource.resolution || 'Original');
    };

    const handleQualityChange = (newResolution) => {
        if (!activeSource) return;
        const videoElement = videoRef.current;
        const currentTime = videoElement ? videoElement.currentTime : 0;
        let targetSource;
        if (newResolution === 'Original') {
            targetSource = sources.find(s => s.provider === activeSource.provider && (s.resolution === null || s.resolution === 'Original'));
        } else {
            targetSource = sources.find(s => s.provider === activeSource.provider && s.resolution === newResolution);
        }
        if (targetSource) {
            setActiveSource(targetSource);
            setCurrentResolution(newResolution);
            setShowQualityMenu(false);
            setTimeout(() => {
                if (videoRef.current) {
                    videoRef.current.currentTime = currentTime;
                    videoRef.current.play().catch(() => console.log('Auto-play prevented'));
                }
            }, 100);
        }
    };

    // Derived state
    const distinctProviders = [...new Set(sources.map(s => s.provider))];
    const currentProviderResolutions = sources
        .filter(s => s.provider === activeSource?.provider)
        .map(s => s.resolution || 'Original')
        .filter((v, i, a) => a.indexOf(v) === i)
        .sort((a, b) => {
            const va = parseInt(a) || 9999;
            const vb = parseInt(b) || 9999;
            return vb - va;
        });

    // Helpers
    const formatViews = (views) => {
        if (views >= 1000000) return (views / 1000000).toFixed(1) + 'M';
        if (views >= 1000) return (views / 1000).toFixed(1) + 'K';
        return views;
    };

    const timeAgo = (dateStr) => {
        const date = new Date(dateStr);
        const now = new Date();
        const diff = Math.floor((now - date) / 1000);
        if (diff < 60) return 'just now';
        if (diff < 3600) return Math.floor(diff / 60) + ' minutes ago';
        if (diff < 86400) return Math.floor(diff / 3600) + ' hours ago';
        if (diff < 2592000) return Math.floor(diff / 86400) + ' days ago';
        if (diff < 31536000) return Math.floor(diff / 2592000) + ' months ago';
        return Math.floor(diff / 31536000) + ' years ago';
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-[#0f0f0f] flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-white"></div>
            </div>
        );
    }

    if (!video) {
        return (
            <div className="min-h-screen bg-[#0f0f0f] flex flex-col items-center justify-center text-white">
                <h2 className="text-2xl font-bold mb-4">Video not found</h2>
                <Link to="/" className="text-blue-500 hover:text-blue-400">Back to Home</Link>
            </div>
        );
    }

    return (
        <div className="min-h-screen w-full bg-[#0f0f0f] text-white">
            {/* ─── YouTube-Style Navbar ─── */}
            <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0f0f0f] h-14 px-4 flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => setSidebarOpen(true)}
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

                <div className="flex-1 max-w-xl mx-4 hidden md:flex items-center">
                    <div className="flex flex-1">
                        <input
                            type="text"
                            placeholder="Search"
                            className="w-full bg-[#121212] border border-gray-700 rounded-l-full py-2 pl-4 pr-4 focus:outline-none focus:border-blue-500 text-sm"
                        />
                        <button className="bg-[#222222] border border-l-0 border-gray-700 px-5 rounded-r-full hover:bg-[#333333] transition-colors">
                            <Search className="w-5 h-5 text-gray-400" />
                        </button>
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    {isAuthenticated ? (
                        <>
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

            {/* ─── Sidebar Overlay ─── */}
            <Sidebar
                isOpen={sidebarOpen}
                categories={categories}
                onClose={() => setSidebarOpen(false)}
                isOverlay={true}
            />

            {/* ─── Main Content ─── */}
            <div className="pt-14 w-full lg:max-w-[1700px] lg:mx-auto flex flex-col lg:flex-row gap-0 lg:gap-8 lg:pt-4">

                {/* ═══ LEFT COLUMN: Player + Info ═══ */}
                <div className="w-full flex-1 min-w-0">

                    {/* ─── Video Player (sticky on mobile) ─── */}
                    <div className="sticky top-14 z-40 lg:static bg-[#0f0f0f]">
                        <div className="w-full aspect-video bg-black overflow-hidden relative lg:rounded-xl">
                            {activeSource ? (
                                activeSource.provider === 'local' || activeSource.provider === 'telegram' ? (
                                    <>
                                        <video
                                            key={`${activeSource.provider}-${activeSource.resolution}`}
                                            ref={videoRef}
                                            controls
                                            autoPlay
                                            className="w-full h-full object-contain bg-black"
                                            src={(activeSource.provider === 'local' || activeSource.provider === 'telegram') ? api.getStreamUrl(video.id, activeSource.resolution) : null}
                                            poster={video.thumbnail_url}
                                            onTimeUpdate={handleTimeUpdate}
                                            onError={() => setPlaybackError(true)}
                                            onPlay={() => setAdOverlayVisible(false)}
                                        >
                                            Your browser does not support the video tag.
                                        </video>

                                        {/* Ad Overlay (Click to Play) */}
                                        {adOverlayVisible && (
                                            <div
                                                className="absolute inset-0 z-20 cursor-pointer flex items-center justify-center bg-black/50 hover:bg-black/40 transition-colors group"
                                                onClick={handleAdClick}
                                            >
                                                <div className="w-16 h-16 sm:w-20 sm:h-20 bg-red-600 rounded-full flex items-center justify-center shadow-2xl group-hover:scale-110 transition-transform">
                                                    <svg className="w-8 h-8 sm:w-10 sm:h-10 text-white fill-current ml-1" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                                                </div>
                                            </div>
                                        )}

                                        {/* Playback Error Overlay */}
                                        {playbackError && (
                                            <div className="absolute inset-0 bg-black/80 flex flex-col items-center justify-center z-10">
                                                <AlertCircle className="w-12 h-12 text-red-500 mb-4" />
                                                <p className="text-white font-medium mb-4">Video failed to load</p>
                                                <button
                                                    onClick={handleReloadVideo}
                                                    className="bg-white text-black px-6 py-2 rounded-full font-medium text-sm hover:bg-gray-200 transition-colors flex items-center gap-2"
                                                >
                                                    <RefreshCw className="w-4 h-4" />
                                                    Retry
                                                </button>
                                            </div>
                                        )}
                                    </>
                                ) : (
                                    <iframe
                                        key={`${activeSource.provider}-${activeSource.resolution}`}
                                        src={activeSource.embed_url}
                                        className="w-full h-full absolute inset-0"
                                        allowFullScreen
                                        scrolling="no"
                                        frameBorder="0"
                                        title={video.title}
                                    ></iframe>
                                )
                            ) : (
                                <div className="flex items-center justify-center w-full h-full bg-gray-900 text-gray-400">
                                    <p>No playable source found.</p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* ─── Responsive Ad unit (Strictly Above Title) ─── */}
                    <div className="w-full px-4 lg:px-0 mt-3 mb-1 flex justify-center overflow-hidden">
                        <div ref={(el) => {
                            if (el && !el.dataset.adLoaded) {
                                el.dataset.adLoaded = 'true';
                                const isMobile = window.innerWidth < 468;
                                const adWidth = isMobile ? 320 : 468;
                                const adHeight = isMobile ? 50 : 60;
                                const configScript = document.createElement('script');
                                configScript.text = `atOptions = {'key':'92ddfa4ed8b775183e950459a641f268','format':'iframe','height':${adHeight},'width':${adWidth},'params':{}};`;
                                el.appendChild(configScript);
                                const invokeScript = document.createElement('script');
                                invokeScript.src = 'https://www.highperformanceformat.com/92ddfa4ed8b775183e950459a641f268/invoke.js';
                                el.appendChild(invokeScript);
                            }
                        }} className="min-h-[50px] sm:min-h-[60px] w-full flex justify-center" />
                    </div>

                    {/* ─── Video Title & Controls Row ─── */}
                    <div className="w-full px-4 lg:px-0 mt-3">
                        <div className="flex items-start justify-between gap-4">
                            <h1 className="text-[18px] sm:text-xl font-bold leading-tight break-words flex-1">
                                {video.title}
                            </h1>

                            {/* Technical Controls (Settings Menu) */}
                            <div className="relative flex-shrink-0">
                                <button
                                    onClick={() => setShowQualityMenu(!showQualityMenu)}
                                    className="p-2 hover:bg-white/10 rounded-full transition-colors text-white"
                                    title="Source & Quality Settings"
                                >
                                    <Settings className={`w-5 h-5 ${showQualityMenu ? 'animate-spin-slow' : ''}`} />
                                </button>

                                {showQualityMenu && (
                                    <div className="absolute top-full right-0 mt-2 bg-[#212121] border border-gray-700 rounded-xl shadow-2xl overflow-hidden min-w-[200px] z-[60]">
                                        {/* Servers */}
                                        <div className="px-3 py-2 border-b border-gray-700 text-[10px] text-gray-400 font-bold uppercase tracking-wider bg-white/5">
                                            Select Server
                                        </div>
                                        <div className="py-1 border-b border-gray-700">
                                            {distinctProviders.map((provider, idx) => (
                                                <button
                                                    key={provider}
                                                    onClick={() => { handleServerChange(provider); }}
                                                    className={`w-full px-3 py-2 text-left text-xs hover:bg-white/10 transition-colors flex items-center justify-between ${activeSource?.provider === provider ? 'text-blue-400' : 'text-gray-300'}`}
                                                >
                                                    <span>Server {idx + 1} ({provider})</span>
                                                    {activeSource?.provider === provider && <div className="w-1.5 h-1.5 bg-blue-400 rounded-full"></div>}
                                                </button>
                                            ))}
                                        </div>

                                        {/* Quality */}
                                        {currentProviderResolutions.length > 1 && (
                                            <>
                                                <div className="px-3 py-2 border-b border-gray-700 text-[10px] text-gray-400 font-bold uppercase tracking-wider bg-white/5">
                                                    Select Quality
                                                </div>
                                                <div className="py-1">
                                                    {currentProviderResolutions.map((res) => (
                                                        <button
                                                            key={res}
                                                            onClick={() => { handleQualityChange(res); setShowQualityMenu(false); }}
                                                            className={`w-full px-3 py-2 text-left text-xs hover:bg-white/10 transition-colors flex items-center justify-between ${currentResolution === res ? 'text-blue-400' : 'text-gray-300'}`}
                                                        >
                                                            <span>{res}</span>
                                                            {currentResolution === res && <div className="w-1.5 h-1.5 bg-blue-400 rounded-full"></div>}
                                                        </button>
                                                    ))}
                                                </div>
                                            </>
                                        )}

                                        <div className="p-1">
                                            <button
                                                onClick={() => { handleManualRefresh(); setShowQualityMenu(false); }}
                                                className="w-full flex items-center gap-2 px-3 py-2 text-[10px] text-gray-500 hover:text-white transition-colors"
                                            >
                                                <RefreshCw className="w-3 h-3" />
                                                Refresh Sources
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* ─── Channel Information & Subscribe Row ─── */}
                    <div className="w-full px-4 lg:px-0 mt-3 flex items-center justify-between">
                        <div className="flex items-center gap-3 min-w-0">
                            <Link to="#" className="flex-shrink-0">
                                {video.uploader?.avatar_url ? (
                                    <img
                                        src={video.uploader.avatar_url}
                                        className="w-9 h-9 sm:w-10 sm:h-10 rounded-full object-cover"
                                        alt="Channel"
                                    />
                                ) : (
                                    <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-full bg-purple-600 flex items-center justify-center font-bold text-sm uppercase text-white leading-none">
                                        {(video.uploader?.display_name || video.uploader?.username || "U")[0]}
                                    </div>
                                )}
                            </Link>

                            <div className="min-w-0">
                                <h3 className="font-bold text-sm sm:text-[15px] leading-tight truncate">
                                    {video.uploader?.display_name || video.uploader?.username || "Unknown"}
                                </h3>
                                <p className="text-[11px] sm:text-xs text-gray-400 mt-0.5 leading-tight">Uploader</p>
                            </div>
                        </div>

                        <div className="flex-shrink-0">
                            <SubscribeButton channelId={video.uploader_id || video.uploader?.id} />
                        </div>
                    </div>

                    {/* ─── Action Buttons Row (Pills) ─── */}
                    <div className="w-full px-4 lg:px-0 mt-4 flex items-center gap-2 overflow-x-auto scrollbar-hide">
                        <div className="flex items-center bg-[#272727] rounded-full overflow-hidden flex-shrink-0">
                            <LikeButton videoId={video.id} />
                        </div>

                        <button
                            onClick={() => navigator.share?.({ title: video.title, url: window.location.href }) || navigator.clipboard.writeText(window.location.href)}
                            className="flex items-center gap-2 bg-[#272727] hover:bg-[#3a3a3a] px-4 py-2 rounded-full text-sm font-medium transition-colors flex-shrink-0"
                        >
                            <Share2 className="w-4 h-4" />
                            <span>Share</span>
                        </button>

                        <button
                            onClick={() => isAuthenticated ? setShowPlaylistModal(true) : alert("Please login to save")}
                            className="flex items-center gap-2 bg-[#272727] hover:bg-[#3a3a3a] px-4 py-2 rounded-full text-sm font-medium transition-colors flex-shrink-0"
                        >
                            <ListPlus className="w-4 h-4" />
                            <span>Save</span>
                        </button>

                        <button className="flex items-center justify-center bg-[#272727] hover:bg-[#3a3a3a] w-9 h-9 rounded-full transition-colors flex-shrink-0">
                            <MoreHorizontal className="w-4 h-4" />
                        </button>
                    </div>

                    {/* ─── Description Box ─── */}
                    <div className="w-full px-4 lg:px-0 mt-4">
                        <div
                            className="bg-[#272727] hover:bg-[#3a3a3a] rounded-xl p-3 cursor-pointer transition-colors"
                            onClick={() => setDescExpanded(!descExpanded)}
                        >
                            <div className="flex items-center gap-2 text-sm font-bold">
                                <span>{formatViews(video.views)} views</span>
                                <span>{timeAgo(video.upload_date)}</span>
                            </div>
                            <div className={`text-sm mt-1 whitespace-pre-wrap ${!descExpanded ? 'line-clamp-2' : ''}`}>
                                {video.description || "No description provided for this video."}
                            </div>
                            <button className="text-sm font-bold mt-1 text-gray-400">
                                {descExpanded ? 'Show less' : '...more'}
                            </button>
                        </div>
                    </div>

                    {/* ─── Comments Section ─── */}
                    <div className="w-full mt-6">
                        <CommentSection videoId={video.id} />
                    </div>

                    {/* ─── Related Videos (Mobile Only) ─── */}
                    <div className="lg:hidden px-4 mt-6 flex flex-col gap-4">
                        <h3 className="text-base font-bold">Related Videos</h3>
                        <div className="flex flex-col gap-3">
                            {relatedVideos.map(vid => (
                                <VideoCard key={vid.id} video={vid} />
                            ))}
                        </div>
                    </div>
                </div>

                {/* ═══ RIGHT COLUMN: Sidebar (Desktop Only) ═══ */}
                <div className="hidden lg:block w-[402px] flex-shrink-0 pt-0 pr-4">
                    {/* Sidebar Ad */}
                    <div className="mb-4">
                        <AdBanner format="square" className="my-0" />
                    </div>

                    <h3 className="text-base font-bold mb-3">Up next</h3>
                    <div className="flex flex-col gap-2">
                        {relatedVideos.map(vid => (
                            <RelatedVideoItem key={vid.id} vid={vid} />
                        ))}
                    </div>
                </div>
            </div>

            {/* Playlist Modal */}
            {showPlaylistModal && (
                <AddToPlaylist
                    videoId={video.id}
                    onClose={() => setShowPlaylistModal(false)}
                />
            )}
        </div>
    );
};

/* ─── Related Video Item Component (YouTube-style) ─── */
const RelatedVideoItem = ({ vid }) => {
    const formatDuration = (seconds) => {
        if (!seconds) return '0:00';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    const formatViews = (views) => {
        if (views >= 1000000) return (views / 1000000).toFixed(1) + 'M views';
        if (views >= 1000) return (views / 1000).toFixed(1) + 'K views';
        return views + ' views';
    };

    const timeAgo = (dateStr) => {
        const date = new Date(dateStr);
        const now = new Date();
        const diff = Math.floor((now - date) / 1000);
        if (diff < 3600) return Math.floor(diff / 60) + ' min ago';
        if (diff < 86400) return Math.floor(diff / 3600) + ' hours ago';
        if (diff < 2592000) return Math.floor(diff / 86400) + ' days ago';
        if (diff < 31536000) return Math.floor(diff / 2592000) + ' months ago';
        return Math.floor(diff / 31536000) + ' years ago';
    };

    return (
        <Link to={`/video/${vid.id}`} className="flex gap-2 group">
            {/* Thumbnail */}
            <div className="relative flex-shrink-0 w-[168px] aspect-video bg-gray-800 rounded-lg overflow-hidden">
                <img src={vid.thumbnail_url} alt={vid.title} className="w-full h-full object-cover" loading="lazy" />
                <span className="absolute bottom-1 right-1 bg-black/80 text-white text-[11px] font-medium px-1 rounded">
                    {formatDuration(vid.duration)}
                </span>
            </div>

            {/* Info */}
            <div className="flex-1 min-w-0 pt-0.5">
                <h4 className="font-medium text-sm leading-tight line-clamp-2 group-hover:text-white transition-colors">
                    {vid.title}
                </h4>
                <p className="text-xs text-gray-400 mt-1.5 leading-tight truncate">
                    {vid.uploader?.display_name || vid.uploader?.username || 'StreamPlatform'}
                </p>
                <p className="text-xs text-gray-400 leading-tight">
                    {formatViews(vid.views)} • {timeAgo(vid.upload_date)}
                </p>
            </div>
        </Link>
    );
};

export default VideoDetails;
