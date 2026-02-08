import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../services/api.js';
import { useAuth } from '../context/AuthContext.jsx';
import { Share2, Eye, Calendar, Settings, User, LogOut, AlertCircle, RefreshCw } from 'lucide-react';
import VideoCard from '../components/video/VideoCard.jsx';
import AdBanner from '../components/layout/AdBanner.jsx';
import LikeButton from '../components/video/LikeButton.jsx';
import CommentSection from '../components/video/CommentSection.jsx';
import SubscribeButton from '../components/video/SubscribeButton.jsx';
import AddToPlaylist from '../components/video/AddToPlaylist.jsx';
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

    // Quality selection state
    const [currentResolution, setCurrentResolution] = useState(null);
    const [showQualityMenu, setShowQualityMenu] = useState(false);
    const [showPlaylistModal, setShowPlaylistModal] = useState(false);
    const [playbackError, setPlaybackError] = useState(false);
    const videoRef = useRef(null);
    const lastSavedTime = useRef(0);
    const initialSeekDone = useRef(false);

    useEffect(() => {
        const fetchVideoData = async () => {
            setLoading(true);
            try {
                const videoData = await api.getVideo(id);
                setVideo(videoData);

                // Prepare Sources
                const videoSources = videoData.sources || [];

                // Helper: deduplicate providers for Server Buttons
                // Groups sources by provider. e.g. { 'streamtape': [source720, source480], 'telegram': [...] }
                // For legacy or single-mode, we might just have one.

                // Add "Primary" source (legacy support)
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

                // Set Default Source Priority: DoodStream -> Telegram -> StreamTape -> Local
                const priority = ['doodstream', 'telegram', 'streamtape', 'local'];

                // Find best provider first
                const uniqueProviders = [...new Set(videoSources.map(s => s.provider))];
                const bestProvider = uniqueProviders.sort((a, b) => priority.indexOf(a) - priority.indexOf(b))[0];

                // Find best resolution for that provider (highest)
                const providerSources = videoSources.filter(s => s.provider === bestProvider);
                // logic to pick highest res or 'Original'
                const bestSource = providerSources[0]; // Simplified for now, can add resolution sorting later

                setActiveSource(bestSource || videoSources[0]);
                setCurrentResolution(bestSource?.resolution || 'Original');

                // Record View
                api.recordView(id);

                // We NO LONGER need independent resolution fetching for Local/Telegram only.
                // We derive available resolutions from the `videoSources` for the current provider.
                // BUT, for Telegram/Local legacy that uses `VideoResolution` table (fetched via api.getVideoResolutions), we might need to merge them?
                // The new system stores everything in `VideoSource`. 
                // Let's assume `VideoSource` is the source of truth for NEW uploads.
                // For OLD uploads (Telegram specific), `api.getVideoResolutions` returns them.
                // We should probably merge them into `sources` state if they aren't already there.
                // However, `videoData.sources` comes from the `Video` relationship.
                // My `upload.py` creates `VideoResolution` (legacy table) AND `VideoSource` (new table) for Telegram.
                // So `video.sources` should have them. 
                // Wait, `upload_video` creates `VideoSource` for the *initial* upload.
                // `background_transcode_and_upload` creates `VideoResolution` (Line 233 in upload.py BEFORE my edit).
                // AFTER my edit, `background_transcode_and_upload` creates `VideoSource` for ALL providers.
                // So `video.sources` SHOULD contain all resolution variants.

                // So we can rely on `videoSources` state.

                // Fetch related videos
                let related = [];
                if (videoData.category && videoData.category.slug) {
                    related = await api.getVideosByCategory(videoData.category.slug, 0, 8);
                } else {
                    related = await api.getVideos(0, 8);
                }
                setRelatedVideos(related.filter(v => v.id !== parseInt(id)));
            } catch (error) {
                console.error("Failed to fetch video details", error);
            } finally {
                setLoading(false);
            }
        };

        if (id) {
            fetchVideoData();
            window.scrollTo(0, 0);
        }
    }, [id]);

    // Force reload video element when active source changes
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

    // Dynamic Polling for background process status
    useEffect(() => {
        let interval;

        const checkProcessing = (currentSources) => {
            if (!currentSources || currentSources.length === 0) return true;
            // New system goal: 3 providers (tg, st, dd) * 3 res (720, 480, 240) = 9
            // If less than 6 (e.g. only original servers done but no transcoding), show processing.
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
            }, 20000); // Poll every 20s
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

    // Resume playback position
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
        if (Math.abs(currentTime - lastSavedTime.current) >= 10) { // Save every 10s
            lastSavedTime.current = currentTime;
            const token = localStorage.getItem('token');
            const total = videoRef.current.duration;
            const completed = total > 0 && (currentTime / total) > 0.9; // 90% = completed
            api.saveProgress(video.id, currentTime, completed, token).catch(e => console.error(e));
        }
    };

    const handleServerChange = (newProvider) => {
        // Find best resolution for this provider
        // Sort by resolution (naive check: looking for digits)
        const providerSources = sources.filter(s => s.provider === newProvider);
        if (providerSources.length === 0) return;

        // Try to keep current resolution if available
        let newSource = providerSources.find(s => s.resolution === currentResolution);

        if (!newSource) {
            // Fallback to highest available
            newSource = providerSources[0]; // Simplified sort logic for now
        }

        setActiveSource(newSource);
        setCurrentResolution(newSource.resolution || 'Original');
    };

    // Handle quality change
    const handleQualityChange = (newResolution) => {
        if (!activeSource) return;

        const videoElement = videoRef.current;
        const currentTime = videoElement ? videoElement.currentTime : 0;

        // Find source with same provider and new resolution
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

            // Note: IFRAME sources (StreamTape) won't support seek restoration this way easily 
            // unless the iframe API supports it. For now, video restarts.
            // HTML5 video will restore.
            setTimeout(() => {
                if (videoRef.current) {
                    videoRef.current.currentTime = currentTime;
                    videoRef.current.play().catch(() => console.log('Auto-play prevented'));
                }
            }, 100);
        }
    };

    // Compute derived state for UI
    const distinctProviders = [...new Set(sources.map(s => s.provider))];
    const currentProviderResolutions = sources
        .filter(s => s.provider === activeSource?.provider)
        .map(s => s.resolution || 'Original')
        .filter((v, i, a) => a.indexOf(v) === i) // Unique
        .sort((a, b) => {
            // Sort high to low
            const va = parseInt(a) || 9999;
            const vb = parseInt(b) || 9999;
            return vb - va;
        });

    if (loading) {
        return (
            <div className="min-h-screen bg-[#1a1a1a] flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-red-600"></div>
            </div>
        );
    }

    if (!video) {
        return (
            <div className="min-h-screen bg-[#1a1a1a] flex flex-col items-center justify-center text-white">
                <h2 className="text-2xl font-bold mb-4">Video not found</h2>
                <Link to="/" className="text-red-500 hover:text-red-400">Back to Home</Link>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[#1a1a1a] text-white w-full overflow-x-hidden">
            {/* Navbar */}
            <nav className="sticky top-0 z-50 bg-[#242424] border-b border-gray-800 px-4 py-3 flex items-center justify-between">
                <Link to="/" className="flex items-center space-x-2">
                    <h1 className="text-xl font-bold tracking-tighter text-red-600">
                        STREAM<span className="text-white">PLATFORM</span>
                    </h1>
                </Link>
                <div className="flex items-center gap-3">
                    {isAuthenticated ? (
                        <>
                            <span className="text-sm text-gray-300 hidden md:block">
                                {user?.display_name || user?.username}
                            </span>
                            <button
                                onClick={logout}
                                className="flex items-center gap-2 bg-white/10 hover:bg-white/20 text-white px-4 py-1.5 rounded-full text-sm font-medium transition-colors"
                            >
                                <LogOut size={16} />
                                Logout
                            </button>
                        </>
                    ) : (
                        <Link
                            to="/auth"
                            className="bg-red-600 hover:bg-red-700 text-white px-4 py-1.5 rounded-full text-sm font-medium transition-colors"
                        >
                            Sign In
                        </Link>
                    )}
                </div>
            </nav>

            <div className="w-full max-w-[1600px] mx-auto p-3 lg:p-6 grid grid-cols-1 lg:grid-cols-3 gap-4 lg:gap-8">
                {/* Main Content: Player + Info */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Player Container */}
                    <div>
                        <div className="aspect-video bg-black rounded-xl overflow-hidden shadow-2xl relative">
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
                                        >
                                            {(activeSource.provider === 'telegram') && (
                                                <p className="text-white p-4 text-center">Telegram playback requires client-side handling or proxy. (Implementation pending)</p>
                                            )}
                                            Your browser does not support the video tag.
                                        </video>

                                        {/* Playback Error Overlay */}
                                        {playbackError && (
                                            <div className="absolute inset-0 bg-black/80 flex flex-col items-center justify-center z-10">
                                                <AlertCircle className="w-12 h-12 text-red-500 mb-4" />
                                                <p className="text-white font-medium mb-4">Video failed to load or timed out.</p>
                                                <button
                                                    onClick={handleReloadVideo}
                                                    className="bg-red-600 hover:bg-red-700 text-white px-6 py-2 rounded-full font-bold transition-colors flex items-center gap-2"
                                                >
                                                    <RefreshCw className="w-4 h-4" />
                                                    Reload Video
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

                        {/* Server & Quality Controls */}
                        <div className="flex flex-wrap items-center justify-between mt-4 gap-4">
                            {/* Server Selector */}
                            <div className="flex items-center space-x-2 overflow-x-auto pb-2">
                                <span className="text-sm font-medium text-gray-400 whitespace-nowrap">Server:</span>
                                {distinctProviders.map((provider, idx) => (
                                    <button
                                        key={provider}
                                        onClick={() => handleServerChange(provider)}
                                        className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${activeSource?.provider === provider
                                            ? 'bg-red-600 text-white'
                                            : 'bg-[#333] hover:bg-[#444] text-gray-300'
                                            }`}
                                    >
                                        Server {idx + 1} ({provider})
                                    </button>
                                ))}

                                <button
                                    onClick={handleManualRefresh}
                                    title="Refresh Servers"
                                    className="p-1.5 bg-[#333] hover:bg-[#444] rounded-lg text-gray-400 hover:text-white transition-colors"
                                >
                                    <RefreshCw className="w-4 h-4" />
                                </button>

                                {isProcessing && (
                                    <div className="flex items-center space-x-2 px-3 py-1 bg-blue-500/10 border border-blue-500/20 rounded-full text-blue-400 text-xs font-medium animate-pulse">
                                        <div className="w-1.5 h-1.5 bg-blue-400 rounded-full"></div>
                                        <span>Processing qualities & servers...</span>
                                    </div>
                                )}
                            </div>

                            {/* Quality Selector (Always shown if resolutions exist) */}
                            {currentProviderResolutions.length > 1 && (
                                <div className="relative">
                                    <button
                                        onClick={() => setShowQualityMenu(!showQualityMenu)}
                                        className="flex items-center space-x-2 bg-[#333] hover:bg-[#444] px-4 py-2 rounded-lg text-sm font-medium transition-colors text-white border border-gray-600"
                                    >
                                        <Settings className="w-4 h-4" />
                                        <span>Quality: {currentResolution}</span>
                                    </button>

                                    {showQualityMenu && (
                                        <div className="absolute bottom-full right-0 mb-2 bg-[#1a1a1a] border border-gray-600 rounded-lg shadow-2xl overflow-hidden min-w-[160px] z-50">
                                            <div className="px-4 py-2 border-b border-gray-700 text-xs text-gray-400 font-medium uppercase tracking-wide">
                                                Select Quality
                                            </div>
                                            <div className="py-1">
                                                {currentProviderResolutions.map((res) => (
                                                    <button
                                                        key={res}
                                                        onClick={() => handleQualityChange(res)}
                                                        className={`w-full px-4 py-3 text-left text-sm hover:bg-white/10 transition-colors flex items-center justify-between ${currentResolution === res
                                                            ? 'text-red-500 font-medium bg-red-500/10'
                                                            : 'text-white'
                                                            }`}
                                                    >
                                                        <span>{res}</span>
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Video Info */}
                    <div>
                        <h1 className="text-xl md:text-2xl font-bold mb-2 break-words leading-tight">{video.title}</h1>

                        <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-gray-800 gap-4">
                            <div className="flex items-center space-x-4 text-sm text-gray-400">
                                <div className="flex items-center">
                                    <Eye className="w-4 h-4 mr-1.5" />
                                    <span>{video.views.toLocaleString()} views</span>
                                </div>
                                <div className="flex items-center">
                                    <Calendar className="w-4 h-4 mr-1.5" />
                                    <span>{new Date(video.upload_date).toLocaleDateString()}</span>
                                </div>
                                {video.original_resolution && (
                                    <span className="bg-red-600/20 text-red-400 px-2 py-0.5 rounded text-xs font-medium">
                                        {video.original_resolution}
                                    </span>
                                )}
                            </div>

                            <div className="flex items-center space-x-4">
                                <LikeButton videoId={video.id} />
                                <button
                                    onClick={() => navigator.share?.({ title: video.title, url: window.location.href }) || navigator.clipboard.writeText(window.location.href)}
                                    className="flex items-center space-x-2 bg-white/10 hover:bg-white/20 px-4 py-2 rounded-full text-sm font-medium transition-colors"
                                >
                                    <Share2 className="w-4 h-4" />
                                    <span>Share</span>
                                </button>
                                <button
                                    onClick={() => isAuthenticated ? setShowPlaylistModal(true) : alert("Please login to save")}
                                    className="flex items-center space-x-2 bg-white/10 hover:bg-white/20 px-4 py-2 rounded-full text-sm font-medium transition-colors"
                                >
                                    <ListPlus className="w-4 h-4" />
                                    <span>Save</span>
                                </button>
                            </div>
                        </div>

                        {/* Description & Channel */}
                        {/* Description & Channel */}
                        <div className="mt-6 flex space-x-4">
                            {/* Avatar */}
                            {video.uploader?.avatar_url ? (
                                <img
                                    src={video.uploader.avatar_url}
                                    className="w-12 h-12 rounded-full object-cover flex-shrink-0"
                                    alt="Uploader"
                                />
                            ) : (
                                <div className="w-12 h-12 rounded-full bg-blue-600 flex items-center justify-center font-bold text-lg flex-shrink-0 uppercase text-white">
                                    {(video.uploader?.display_name || video.uploader?.username || "U")[0]}
                                </div>
                            )}

                            <div className="flex-1">
                                <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                                    <div>
                                        <h3 className="font-bold text-lg">
                                            {video.uploader?.display_name || video.uploader?.username || "Unknown User"}
                                        </h3>
                                        <div className="mt-1">
                                            <SubscribeButton channelId={video.uploader_id || video.uploader?.id} />
                                        </div>
                                    </div>
                                </div>

                                <div className="bg-[#242424] p-4 rounded-xl text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">
                                    <p className="font-medium text-white mb-2">Category: <span className="text-red-500">{video.category?.name}</span></p>
                                    <p className="break-words">{video.description || "No description provided for this video."}</p>
                                </div>
                            </div>
                        </div>

                        {/* Comments Section */}
                        <CommentSection videoId={video.id} />
                    </div>
                </div>

                {/* Sidebar: Related Videos */}
                <div className="lg:col-span-1">
                    <AdBanner format="square" />
                    <h3 className="text-lg font-bold mb-4 mt-6">Up Next</h3>
                    <div className="flex flex-col space-y-4">
                        {relatedVideos.map(vid => (
                            <div key={vid.id} className="group flex gap-3 cursor-pointer hover:bg-white/5 p-2 rounded-lg transition-colors w-full overflow-hidden">
                                <Link to={`/video/${vid.id}`} className="flex-shrink-0 w-32 md:w-36 relative aspect-video bg-gray-800 rounded-lg overflow-hidden">
                                    <img src={vid.thumbnail_url} alt={vid.title} className="w-full h-full object-cover" loading="lazy" />
                                    <span className="absolute bottom-1 right-1 bg-black/80 text-white text-[10px] px-1 rounded">
                                        {new Date(vid.duration * 1000).toISOString().substr(14, 5)}
                                    </span>
                                </Link>
                                <div className="flex flex-col flex-1 min-w-0">
                                    <Link to={`/video/${vid.id}`}>
                                        <h4 className="font-semibold text-sm line-clamp-2 title-font group-hover:text-red-500 transition-colors">
                                            {vid.title}
                                        </h4>
                                    </Link>
                                    <p className="text-gray-400 text-xs mt-1">StreamPlatform</p>
                                    <div className="flex items-center text-gray-500 text-xs mt-1 space-x-2">
                                        <span>{vid.views > 1000 ? (vid.views / 1000).toFixed(1) + 'K' : vid.views} views</span>
                                        <span>•</span>
                                        <span>{new Date(vid.upload_date).toLocaleDateString()}</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Playlist Modal */}
            {
                showPlaylistModal && (
                    <AddToPlaylist
                        videoId={video.id}
                        onClose={() => setShowPlaylistModal(false)}
                    />
                )
            }
        </div >
    );
};

export default VideoDetails;
