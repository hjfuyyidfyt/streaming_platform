import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext.jsx';
import { api } from '../../services/api.js';
import {
    MessageCircle,
    Heart,
    Trash2,
    Reply,
    Send,
    Sparkles,
    User,
    ChevronDown
} from 'lucide-react';
import './CommentSection.css';

const CommentSection = ({ videoId }) => {
    const { user, token, isAuthenticated } = useAuth();
    const [comments, setComments] = useState([]);
    const [loading, setLoading] = useState(true);
    const [newComment, setNewComment] = useState('');
    const [replyTo, setReplyTo] = useState(null);
    const [replyContent, setReplyContent] = useState('');
    const [showSuperChat, setShowSuperChat] = useState(false);
    const [superChatAmount, setSuperChatAmount] = useState(5);
    const [total, setTotal] = useState(0);

    useEffect(() => {
        loadComments();
    }, [videoId]);

    const loadComments = async () => {
        try {
            const data = await api.getComments(videoId);
            setComments(data.comments || []);
            setTotal(data.total || 0);
        } catch (err) {
            console.error('Failed to load comments:', err);
        } finally {
            setLoading(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!newComment.trim() || !isAuthenticated) return;

        try {
            const superChat = showSuperChat ? { amount: superChatAmount } : null;
            const comment = await api.addComment(videoId, newComment, null, superChat, token);
            setComments([comment, ...comments]);
            setNewComment('');
            setShowSuperChat(false);
            setTotal(total + 1);
        } catch (err) {
            console.error('Failed to add comment:', err);
        }
    };

    const handleReply = async (parentId) => {
        if (!replyContent.trim() || !isAuthenticated) return;

        try {
            const reply = await api.addComment(videoId, replyContent, parentId, null, token);
            // Add reply to parent comment
            setComments(comments.map(c => {
                if (c.id === parentId) {
                    return { ...c, replies: [...(c.replies || []), reply] };
                }
                return c;
            }));
            setReplyTo(null);
            setReplyContent('');
        } catch (err) {
            console.error('Failed to reply:', err);
        }
    };

    const handleLike = async (commentId) => {
        if (!isAuthenticated) return;

        try {
            await api.likeComment(commentId, token);
            // Update comment likes count locally
            setComments(comments.map(c => {
                if (c.id === commentId) {
                    return { ...c, likes_count: c.likes_count + 1 };
                }
                if (c.replies) {
                    return {
                        ...c,
                        replies: c.replies.map(r =>
                            r.id === commentId ? { ...r, likes_count: r.likes_count + 1 } : r
                        )
                    };
                }
                return c;
            }));
        } catch (err) {
            console.error('Failed to like comment:', err);
        }
    };

    const handleDelete = async (commentId) => {
        if (!isAuthenticated) return;

        try {
            await api.deleteComment(commentId, token);
            setComments(comments.filter(c => c.id !== commentId));
            setTotal(total - 1);
        } catch (err) {
            console.error('Failed to delete comment:', err);
        }
    };

    const formatTimeAgo = (dateStr) => {
        const date = new Date(dateStr);
        const now = new Date();
        const diff = Math.floor((now - date) / 1000);

        if (diff < 60) return 'Just now';
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
        return date.toLocaleDateString();
    };

    return (
        <div className="comment-section">
            <h3 className="comment-header">
                <MessageCircle size={24} />
                {total} Comments
            </h3>

            {/* Comment Input */}
            {isAuthenticated ? (
                <form onSubmit={handleSubmit} className="comment-form">
                    <div className="comment-input-wrapper">
                        <div className="user-avatar">
                            {user?.avatar_url ? (
                                <img src={user.avatar_url} alt={user.display_name} />
                            ) : (
                                <User size={20} />
                            )}
                        </div>
                        <input
                            type="text"
                            placeholder="Add a comment..."
                            value={newComment}
                            onChange={(e) => setNewComment(e.target.value)}
                            className="comment-input"
                        />
                        <button
                            type="button"
                            className={`super-chat-toggle ${showSuperChat ? 'active' : ''}`}
                            onClick={() => setShowSuperChat(!showSuperChat)}
                            title="Super Chat"
                        >
                            <Sparkles size={18} />
                        </button>
                        <button type="submit" className="send-btn" disabled={!newComment.trim()}>
                            <Send size={18} />
                        </button>
                    </div>

                    {showSuperChat && (
                        <div className="super-chat-panel">
                            <span>💰 Super Chat Amount: $</span>
                            <input
                                type="number"
                                min="1"
                                max="500"
                                value={superChatAmount}
                                onChange={(e) => setSuperChatAmount(Number(e.target.value))}
                            />
                            <span className="super-chat-color" style={{
                                background: superChatAmount >= 100 ? '#ff0000' :
                                    superChatAmount >= 50 ? '#ff6600' :
                                        superChatAmount >= 20 ? '#ffcc00' : '#00cc00'
                            }} />
                        </div>
                    )}
                </form>
            ) : (
                <div className="login-prompt">
                    <a href="/auth">Sign in</a> to comment
                </div>
            )}

            {/* Comments List */}
            <div className="comments-list">
                {loading ? (
                    <div className="loading">Loading comments...</div>
                ) : comments.length === 0 ? (
                    <div className="no-comments">No comments yet. Be the first!</div>
                ) : (
                    comments.map(comment => (
                        <CommentItem
                            key={comment.id}
                            comment={comment}
                            onLike={handleLike}
                            onDelete={handleDelete}
                            onReply={(id) => {
                                setReplyTo(id);
                                setReplyContent('');
                            }}
                            replyTo={replyTo}
                            replyContent={replyContent}
                            setReplyContent={setReplyContent}
                            handleReply={handleReply}
                            formatTimeAgo={formatTimeAgo}
                            currentUserId={user?.id}
                            isAuthenticated={isAuthenticated}
                        />
                    ))
                )}
            </div>
        </div>
    );
};

const CommentItem = ({
    comment,
    onLike,
    onDelete,
    onReply,
    replyTo,
    replyContent,
    setReplyContent,
    handleReply,
    formatTimeAgo,
    currentUserId,
    isAuthenticated,
    isReply = false
}) => {
    const [showReplies, setShowReplies] = useState(true);

    return (
        <div
            className={`comment-item ${isReply ? 'is-reply' : ''} ${comment.is_super_chat ? 'super-chat' : ''}`}
            style={comment.is_super_chat ? { borderColor: comment.super_chat_color } : {}}
        >
            {comment.is_super_chat && (
                <div className="super-chat-badge" style={{ background: comment.super_chat_color }}>
                    💰 ${comment.super_chat_amount}
                </div>
            )}

            <div className="comment-avatar">
                {comment.user?.avatar_url ? (
                    <img src={comment.user.avatar_url} alt={comment.user.display_name} />
                ) : (
                    <User size={isReply ? 16 : 20} />
                )}
            </div>

            <div className="comment-body">
                <div className="comment-meta">
                    <span className="comment-author">
                        {comment.user?.display_name || comment.user?.username || 'User'}
                    </span>
                    <span className="comment-time">{formatTimeAgo(comment.created_at)}</span>
                    {comment.is_edited && <span className="edited-tag">(edited)</span>}
                </div>

                <p className="comment-text">{comment.content}</p>

                <div className="comment-actions">
                    <button onClick={() => onLike(comment.id)} disabled={!isAuthenticated}>
                        <Heart size={14} /> {comment.likes_count || 0}
                    </button>
                    {!isReply && (
                        <button onClick={() => onReply(comment.id)} disabled={!isAuthenticated}>
                            <Reply size={14} /> Reply
                        </button>
                    )}
                    {currentUserId === comment.user_id && (
                        <button className="delete-btn" onClick={() => onDelete(comment.id)}>
                            <Trash2 size={14} />
                        </button>
                    )}
                </div>

                {/* Reply Input */}
                {replyTo === comment.id && (
                    <div className="reply-input">
                        <input
                            type="text"
                            placeholder="Write a reply..."
                            value={replyContent}
                            onChange={(e) => setReplyContent(e.target.value)}
                            autoFocus
                        />
                        <button onClick={() => handleReply(comment.id)}>
                            <Send size={14} />
                        </button>
                        <button className="cancel-btn" onClick={() => onReply(null)}>Cancel</button>
                    </div>
                )}

                {/* Replies */}
                {!isReply && comment.replies && comment.replies.length > 0 && (
                    <div className="replies-section">
                        <button
                            className="show-replies"
                            onClick={() => setShowReplies(!showReplies)}
                        >
                            <ChevronDown className={showReplies ? 'rotated' : ''} size={16} />
                            {comment.replies.length} replies
                        </button>
                        {showReplies && (
                            <div className="replies-list">
                                {comment.replies.map(reply => (
                                    <CommentItem
                                        key={reply.id}
                                        comment={reply}
                                        onLike={onLike}
                                        onDelete={onDelete}
                                        onReply={onReply}
                                        replyTo={replyTo}
                                        replyContent={replyContent}
                                        setReplyContent={setReplyContent}
                                        handleReply={handleReply}
                                        formatTimeAgo={formatTimeAgo}
                                        currentUserId={currentUserId}
                                        isAuthenticated={isAuthenticated}
                                        isReply={true}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

export default CommentSection;
