"""Web UI channel - sidebar navigation + chat + dashboard + practice + review."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from studybot.bus import InboundMessage, MessageBus, OutboundMessage
from studybot.channels.practice import PracticeManager
from studybot.channels.review import ReviewManager
from studybot.channels.memory import MemoryManager


PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Studybot</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release/build/highlight.min.js"></script>
<style>
:root{--bg:#ffffff;--bg-secondary:#f4f4f6;--bg-tertiary:#e8e8ec;--fg:#1a1a1a;--fg-secondary:#71717a;--fg-muted:#a1a1aa;--border:#e5e7eb;--primary:#2563eb;--primary-hover:#1d4ed8;--primary-light:#dbeafe;--user-bg:#2563eb;--user-fg:#ffffff;--bot-bg:#f4f4f6;--bot-fg:#1a1a1a;--danger:#ef4444;--success:#10b981;--warning:#f59e0b;--sidebar-bg:#fafafa;--sidebar-hover:#f0f0f0;--sidebar-active:#e8e8ec;--header-bg:rgba(255,255,255,0.85);--shadow:0 1px 3px rgba(0,0,0,0.06);--shadow-lg:0 4px 12px rgba(0,0,0,0.08);--radius-sm:6px;--radius-md:10px;--radius-lg:18px;--sidebar-w:240px}
.dark{--bg:#18181b;--bg-secondary:#27272a;--bg-tertiary:#3f3f46;--fg:#f4f4f6;--fg-secondary:#a1a1aa;--fg-muted:#6b7280;--border:#3f3f46;--primary:#60a5fa;--primary-hover:#3b82f6;--primary-light:#1e3a5f;--user-bg:#3b82f6;--user-fg:#ffffff;--bot-bg:#27272a;--bot-fg:#f4f4f6;--danger:#f87171;--success:#34d399;--warning:#fbbf24;--sidebar-bg:#1c1c1f;--sidebar-hover:#27272a;--sidebar-active:#3f3f46;--header-bg:rgba(24,24,27,0.90);--shadow:0 1px 3px rgba(0,0,0,0.3);--shadow-lg:0 4px 12px rgba(0,0,0,0.4)}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--fg);transition:background .2s,color .2s;line-height:1.6;font-size:15px;-webkit-font-smoothing:antialiased}
.app{display:flex;height:100vh;overflow:hidden}
/* Sidebar */
.sidebar{width:var(--sidebar-w);background:var(--sidebar-bg);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;overflow:hidden;transition:width .25s,margin .25s,opacity .2s}
.sidebar.collapsed{width:0;opacity:0;margin-left:calc(var(--sidebar-w)*-1);pointer-events:none}
.sidebar-header{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--border);flex-shrink:0;min-height:56px}
.sidebar-header svg{flex-shrink:0}
.sidebar-header h1{font-size:16px;font-weight:600;letter-spacing:-.3px}
.sidebar-header .sub{font-size:11px;color:var(--fg-secondary);display:block;margin-top:-1px}
.sidebar-nav{flex:1;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:2px}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:var(--radius-sm);cursor:pointer;color:var(--fg-secondary);font-size:14px;transition:all .12s;border:none;background:none;width:100%;text-align:left;font-family:inherit}
.nav-item:hover{background:var(--sidebar-hover);color:var(--fg)}
.nav-item.active{background:var(--sidebar-active);color:var(--fg);font-weight:500}
.nav-item .nav-icon{font-size:16px;width:22px;text-align:center;flex-shrink:0}
.nav-item .badge{margin-left:auto;font-size:10px;background:var(--primary);color:#fff;border-radius:10px;padding:1px 7px;font-weight:600}
.nav-section-title{font-size:11px;font-weight:600;color:var(--fg-muted);padding:12px 12px 4px;text-transform:uppercase;letter-spacing:.5px}
.sidebar-footer{padding:10px 12px;border-top:1px solid var(--border);flex-shrink:0;display:flex;align-items:center;gap:8px}
.sidebar-footer .dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.sidebar-footer .dot.online{background:var(--success);box-shadow:0 0 5px var(--success)}
.sidebar-footer .dot.offline{background:var(--danger)}
.sidebar-footer .dot.connecting{background:var(--warning);animation:pulse 1.5s infinite}
.sidebar-footer .s-label{font-size:12px;color:var(--fg-muted);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* Main area */
.main{flex:1;display:flex;flex-direction:column;min-width:0;position:relative}
.topbar{display:flex;align-items:center;gap:10px;padding:0 16px;height:56px;flex-shrink:0;border-bottom:1px solid var(--border);background:var(--header-bg);-webkit-backdrop-filter:blur(12px);backdrop-filter:blur(12px)}
.topbar .menu-btn{background:none;border:none;font-size:20px;cursor:pointer;color:var(--fg-secondary);padding:4px;border-radius:var(--radius-sm)}
.topbar .menu-btn:hover{background:var(--bg-secondary)}
.topbar-title{font-size:15px;font-weight:500;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.topbar-actions{display:flex;align-items:center;gap:6px}
.theme-btn{background:none;border:1px solid var(--border);border-radius:var(--radius-sm);width:30px;height:30px;display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--fg-secondary);transition:all .15s;font-size:15px}
.theme-btn:hover{background:var(--bg-secondary);color:var(--fg)}
/* Views */
.views{flex:1;position:relative;overflow:hidden}
.view{position:absolute;inset:0;overflow-y:auto;display:none}
.view.active{display:flex;flex-direction:column}
/* Chat view */
.chat{flex:1;overflow-y:auto;padding:20px 0}
.chat-inner{max-width:700px;width:100%;margin:0 auto;padding:0 20px;display:flex;flex-direction:column;gap:16px;flex:1;min-height:100%;justify-content:flex-end}
.msg{max-width:85%;padding:10px 16px;line-height:1.7;font-size:15px;word-break:break-word;animation:fadeIn .2s ease-out}
.msg.user{background:var(--user-bg);color:var(--user-fg);align-self:flex-end;border-radius:var(--radius-lg) var(--radius-lg) 4px var(--radius-lg)}
.msg.assistant{background:var(--bot-bg);color:var(--bot-fg);align-self:flex-start;border-radius:var(--radius-lg) var(--radius-lg) var(--radius-lg) 4px;border:1px solid var(--border)}
.msg .msg-meta{font-size:11px;color:inherit;opacity:.5;margin-top:6px}
.msg.user .msg-meta{text-align:right}
.msg.assistant h1,.msg.assistant h2,.msg.assistant h3{margin:12px 0 6px;font-weight:600;line-height:1.4}
.msg.assistant h1{font-size:18px}.msg.assistant h2{font-size:16px}.msg.assistant h3{font-size:15px}
.msg.assistant p{margin:6px 0}.msg.assistant p:first-child{margin-top:0}.msg.assistant p:last-child{margin-bottom:0}
.msg.assistant ul,.msg.assistant ol{margin:6px 0;padding-left:20px}.msg.assistant li{margin:2px 0}
.msg.assistant code{background:var(--bg-tertiary);padding:1px 5px;border-radius:4px;font-size:13px;font-family:'JetBrains Mono','Fira Code','Consolas',monospace}
.msg.assistant pre{margin:8px 0;border-radius:var(--radius-md);overflow:hidden;border:1px solid var(--border);background:#1e1e2e!important}
.msg.assistant pre code{background:none!important;padding:0!important;font-size:13px;display:block;overflow-x:auto}
.msg.assistant blockquote{border-left:3px solid var(--primary);padding:4px 12px;margin:6px 0;color:var(--fg-secondary);background:var(--bg-secondary);border-radius:0 var(--radius-sm) var(--radius-sm) 0}
.msg.assistant table{border-collapse:collapse;margin:8px 0;width:100%;font-size:14px}
.msg.assistant th,.msg.assistant td{border:1px solid var(--border);padding:6px 10px;text-align:left}
.msg.assistant th{background:var(--bg-secondary);font-weight:600}
.msg.assistant a{color:var(--primary);text-decoration:none}.msg.assistant a:hover{text-decoration:underline}
.msg.assistant hr{margin:12px 0;border:none;border-top:1px solid var(--border)}
.stream-cursor{display:inline-block;width:6px;height:16px;background:var(--primary);margin-left:2px;vertical-align:middle;animation:blink 1s step-end infinite}
@keyframes blink{50%{opacity:0}}@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
/* Empty state */
.empty-state{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;color:var(--fg-muted);text-align:center;padding:40px 20px;min-height:300px}
.empty-state .icon{font-size:40px;opacity:.5}.empty-state h3{font-size:16px;font-weight:500;color:var(--fg-secondary)}
.empty-state p{font-size:13px;max-width:360px;line-height:1.5}
/* Input */
.input-area{flex-shrink:0;border-top:1px solid var(--border);padding:10px 20px 14px;background:var(--bg)}
.input-inner{max-width:700px;margin:0 auto;display:flex;gap:8px;align-items:flex-end}
.input-inner textarea{flex:1;resize:none;padding:10px 14px;border-radius:var(--radius-md);border:1px solid var(--border);background:var(--bg-secondary);color:var(--fg);font-size:14px;line-height:1.5;font-family:inherit;outline:none;min-height:42px;max-height:200px;transition:border-color .15s}
.input-inner textarea:focus{border-color:var(--primary)}
.input-inner textarea::placeholder{color:var(--fg-muted)}
.input-actions{display:flex;gap:6px;align-items:center;flex-shrink:0}
.action-btn{width:38px;height:38px;border-radius:var(--radius-md);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .15s;background:var(--bg-secondary);color:var(--fg-secondary);font-size:16px;flex-shrink:0}
.action-btn:hover{background:var(--bg-tertiary);color:var(--fg)}
.send-btn{background:var(--primary);color:#fff;border-color:var(--primary)}
.send-btn:hover{background:var(--primary-hover);border-color:var(--primary-hover)}
.send-btn:disabled{opacity:.4;cursor:not-allowed}
.send-btn.streaming{background:var(--danger);border-color:var(--danger)}
.send-btn.streaming:hover{opacity:.8}
#fileInput{display:none}
.file-chip{font-size:12px;background:var(--primary-light);color:var(--primary);padding:3px 10px;border-radius:20px;display:inline-flex;align-items:center;gap:4px;margin-bottom:4px;align-self:flex-end;max-width:85%}
.file-chip .remove-file{background:none;border:none;color:inherit;font-size:14px;padding:0 2px;cursor:pointer;font-weight:700;opacity:.7}
.file-chip .remove-file:hover{opacity:1}
.drag-overlay{position:fixed;inset:0;z-index:999;background:rgba(37,99,235,0.06);border:3px dashed var(--primary);pointer-events:none;display:none}
.drag-overlay.active{display:block}
.drag-overlay-inner{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);color:var(--primary);font-size:16px;font-weight:500}
/* Banks view */
.banks-view{padding:24px;overflow-y:auto;max-width:800px;margin:0 auto;width:100%}
.banks-view h2{font-size:20px;margin-bottom:4px}.banks-view .subtitle{font-size:13px;color:var(--fg-secondary);margin-bottom:20px}
.bank-card{background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-md);padding:16px;margin-bottom:12px;transition:box-shadow .15s}
.bank-card:hover{box-shadow:var(--shadow)}
.bank-card .bank-name{font-size:15px;font-weight:600;margin-bottom:4px;display:flex;align-items:center;gap:8px}
.bank-card .bank-name .bank-count{font-size:12px;font-weight:400;color:var(--fg-muted)}
.bank-card .bank-domains{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.domain-tag{font-size:11px;background:var(--primary-light);color:var(--primary);padding:2px 8px;border-radius:12px}
.banks-empty{padding:60px 20px;text-align:center;color:var(--fg-muted)}
.banks-empty .icon{font-size:48px;margin-bottom:12px;opacity:.4}
.bank-actions{display:flex;gap:6px;margin-top:8px}
.bank-actions button{font-size:12px;padding:4px 10px;border-radius:var(--radius-sm);border:1px solid var(--border);background:var(--bg);color:var(--fg-secondary);cursor:pointer;font-family:inherit;transition:all .12s}
.bank-actions button:hover{background:var(--bg-tertiary);color:var(--fg)}
.bank-actions button.danger{color:var(--danger);border-color:var(--danger)}
.bank-actions button.danger:hover{background:rgba(239,68,68,0.08)}
.bank-actions button.primary{color:var(--primary);border-color:var(--primary)}
.bank-actions button.primary:hover{background:var(--primary-light)}
/* Question list modal */
.qmodal{position:fixed;inset:0;z-index:1001;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,.35);-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}
.qmodal.active{display:flex}
.qmodal-box{background:var(--bg);border-radius:var(--radius-lg);width:90%;max-width:700px;max-height:80vh;display:flex;flex-direction:column;box-shadow:var(--shadow-lg)}
.qmodal-header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--border);flex-shrink:0}
.qmodal-header h3{font-size:16px;font-weight:600}
.qmodal-close{background:none;border:none;font-size:20px;color:var(--fg-muted);cursor:pointer;padding:0 4px}
.qmodal-close:hover{color:var(--fg)}
.qmodal-body{flex:1;overflow-y:auto;padding:12px 20px 20px}
.qmodal-body .qitem{padding:12px 0;border-bottom:1px solid var(--border)}
.qmodal-body .qitem:last-child{border:none}
.qitem-q{font-size:14px;line-height:1.6;margin-bottom:4px;color:var(--fg)}
.qitem-a{font-size:13px;color:var(--fg-secondary)}
.qitem-kp{font-size:11px;color:var(--primary);margin-top:3px;display:flex;gap:3px;flex-wrap:wrap}
.qitem-kp span{background:var(--primary-light);padding:1px 6px;border-radius:8px}
.qitem-diff{font-size:11px;color:var(--fg-muted);margin-left:auto}
/* Progress view */
.progress-view{padding:24px;overflow-y:auto;max-width:800px;margin:0 auto;width:100%}
.progress-view h2{font-size:20px;margin-bottom:4px}.progress-view .subtitle{font-size:13px;color:var(--fg-secondary);margin-bottom:20px}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:24px}
.stat-card{background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-md);padding:16px;text-align:center;transition:box-shadow .15s}
.stat-card:hover{box-shadow:var(--shadow)}
.stat-card .stat-value{font-size:28px;font-weight:700;color:var(--primary);line-height:1.2}
.stat-card .stat-label{font-size:12px;color:var(--fg-secondary);margin-top:4px}
.stat-card .stat-icon{font-size:24px;margin-bottom:6px}
.progress-section h3{font-size:15px;font-weight:600;margin-bottom:12px;color:var(--fg-secondary)}
.domain-bar{margin-bottom:8px}
.domain-bar .bar-label{display:flex;justify-content:space-between;font-size:13px;margin-bottom:3px}
.domain-bar .bar-label span:last-child{color:var(--fg-muted)}
.domain-bar .bar-track{height:8px;background:var(--bg-tertiary);border-radius:4px;overflow:hidden}
.domain-bar .bar-fill{height:100%;border-radius:4px;background:var(--primary);transition:width .6s ease}
.activity-list{list-style:none;padding:0}
.activity-item{display:flex;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);font-size:13px}
.activity-item:last-child{border:none}
.activity-item .act-icon{font-size:16px;flex-shrink:0;width:20px;text-align:center}
.activity-item .act-text{flex:1;color:var(--fg-secondary)}
.activity-item .act-time{color:var(--fg-muted);font-size:12px;white-space:nowrap}
/* Settings view */
.settings-view{padding:24px;overflow-y:auto;max-width:600px;margin:0 auto;width:100%}
.settings-view h2{font-size:20px;margin-bottom:4px}.settings-view .subtitle{font-size:13px;color:var(--fg-secondary);margin-bottom:20px}
.settings-group{margin-bottom:20px}
.settings-group h3{font-size:14px;font-weight:600;margin-bottom:8px;color:var(--fg-secondary)}
.setting-row{display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-sm);margin-bottom:6px}
.setting-row .s-label{font-size:14px}.setting-row .s-hint{font-size:12px;color:var(--fg-muted);margin-top:1px}
.setting-row input{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--fg);font-size:13px;font-family:inherit;outline:none;width:200px}
.setting-row input:focus{border-color:var(--primary)}
.setting-row select{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 10px;color:var(--fg);font-size:13px;font-family:inherit;outline:none;cursor:pointer}
.save-btn{background:var(--primary);color:#fff;border:none;padding:8px 20px;border-radius:var(--radius-sm);font-size:14px;cursor:pointer;font-weight:500;transition:all .12s;box-shadow:0 1px 3px rgba(0,0,0,0.08)}
.save-btn:hover{background:var(--primary-hover);box-shadow:0 2px 6px rgba(0,0,0,0.12)}
.save-btn:active{transform:scale(.97)}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--fg);color:var(--bg);padding:8px 18px;border-radius:var(--radius-md);font-size:13px;z-index:999;animation:fadeIn .2s;display:none}
/* Upload loading overlay */
.upload-loading{position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:1000;display:none;align-items:center;justify-content:center;-webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px)}
.upload-loading.active{display:flex}
.upload-loading-box{background:var(--bg);border-radius:var(--radius-lg);padding:32px 40px;text-align:center;box-shadow:var(--shadow-lg);max-width:360px}
.upload-spinner{width:36px;height:36px;border:3px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:spin .7s linear infinite;margin:0 auto 14px}
@keyframes spin{to{transform:rotate(360deg)}}
.upload-status{font-size:14px;color:var(--fg);margin-bottom:4px;font-weight:500}
.upload-sub{font-size:12px;color:var(--fg-muted)}
/* Practice view */
.practice-view{padding:24px;overflow-y:auto;max-width:1100px;margin:0 auto;width:100%;display:flex;flex-direction:column;flex:1}
.pv-mode-selector{display:flex;flex-direction:column;align-items:center;justify-content:center;flex:1;gap:24px;padding:40px 20px}
.pv-mode-selector h2{font-size:20px;margin:0}
.pv-mode-cards{display:flex;gap:20px;flex-wrap:wrap;justify-content:center}
.pv-mode-card{width:260px;padding:32px 24px;border:2px solid var(--border);border-radius:var(--radius-lg);cursor:pointer;text-align:center;transition:all .2s;background:var(--bg-secondary)}
.pv-mode-card:hover{border-color:var(--primary);box-shadow:0 4px 16px rgba(37,99,235,0.12);transform:translateY(-2px)}
.pv-mode-icon{font-size:48px;margin-bottom:12px}
.pv-mode-title{font-size:16px;font-weight:600;margin-bottom:6px}
.pv-mode-desc{font-size:13px;color:var(--fg-secondary);line-height:1.5}
.pv-content{display:flex;flex-direction:row;gap:24px;flex:1;align-items:flex-start}
.pv-back-btn{background:none;border:1px solid var(--border);border-radius:var(--radius-sm);width:32px;height:32px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:16px;color:var(--fg-secondary);flex-shrink:0;margin-top:2px}
.pv-back-btn:hover{background:var(--bg-secondary);color:var(--fg)}

.pv-main{flex:1;display:flex;flex-direction:column;gap:12px;min-width:0}

.pv-header h2{font-size:20px;margin-bottom:2px}.pv-header p{font-size:13px;color:var(--fg-secondary);margin:2px 0 0}

.pv-controls{display:flex;flex-direction:column;gap:10px;padding:0}

.pv-filter-group label{font-size:12px;color:var(--fg-muted);display:block;margin-bottom:4px;font-weight:500}

.pv-chips{display:flex;flex-wrap:wrap;gap:4px}

.chip{padding:5px 14px;border-radius:14px;border:1.5px solid var(--border);background:var(--bg);color:var(--fg);cursor:pointer;font-size:13px;transition:all .12s;user-select:none;font-family:inherit;box-shadow:0 1px 2px rgba(0,0,0,0.04)}
.chip:hover{border-color:#1976d2;background:rgba(25,118,210,0.06);color:#1976d2}
.chip:active{transform:scale(.95)}
.chip.active{background:#1976d2;color:#fff;border-color:#1976d2;box-shadow:0 2px 6px rgba(25,118,210,0.25)}

.pv-sidebar{width:260px;flex-shrink:0;display:flex;flex-direction:column;gap:12px}

.pv-question{background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-md);padding:20px;line-height:1.8;font-size:15px;min-height:80px;flex:1}

.pv-eval{border-radius:var(--radius-md);padding:18px;line-height:1.8;font-size:14px;display:none}

.pv-eval.good{background:rgba(16,185,129,0.08);border:1px solid var(--success);display:block}

.pv-eval.bad{background:rgba(239,68,68,0.08);border:1px solid var(--danger);display:block}

.pv-eval-score{font-size:22px;font-weight:700;margin-bottom:10px}

.pv-eval-feedback{color:var(--fg);margin-bottom:10px;line-height:1.8;word-break:break-word;white-space:pre-wrap}

.pv-eval-missing{color:var(--fg-secondary);font-size:13px}

.pv-eval-missing::before{content:'📌 疏漏: ';color:var(--warning);font-weight:600}

.pv-answer{flex:1 1 auto;display:flex}

.pv-answer textarea{width:100%;resize:vertical;padding:14px 16px;border-radius:var(--radius-md);border:1px solid var(--border);background:var(--bg-secondary);color:var(--fg);font-size:14px;line-height:1.6;font-family:inherit;outline:none;min-height:120px;flex:1;transition:border-color .15s}

.pv-answer textarea:focus{border-color:var(--primary)}
.pv-actions{display:flex;gap:8px;align-items:center}
/* Review view */
.review-view{padding:24px;overflow-y:auto;max-width:800px;margin:0 auto;width:100%;display:flex;flex-direction:column;flex:1;gap:16px}

.rv-header h2{font-size:20px;margin-bottom:2px}.rv-header .subtitle{font-size:13px;color:var(--fg-secondary)}

.rv-empty{text-align:center;padding:80px 20px;color:var(--fg-muted)}.rv-empty .icon{font-size:56px;margin-bottom:12px;opacity:.4}

.rv-empty h3{font-size:18px;font-weight:500;color:var(--fg-secondary);margin-bottom:6px}.rv-empty p{font-size:14px}

.rv-card{background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-lg);padding:28px;box-shadow:var(--shadow);animation:fadeIn .3s;flex:1;display:flex;flex-direction:column}

.rv-domain-tag{font-size:11px;background:var(--primary-light);color:var(--primary);padding:2px 10px;border-radius:12px;display:inline-block;margin-bottom:12px}

.rv-label{font-size:11px;font-weight:600;color:var(--fg-muted);text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}

.rv-question{font-size:16px;line-height:1.7;margin-bottom:8px;flex:1}

.rv-divider{border:none;border-top:1px solid var(--border);margin:16px 0}

.rv-answer{font-size:15px;line-height:1.7;color:var(--fg);margin-bottom:12px}

.rv-key-points-label{font-size:13px;font-weight:600;color:var(--warning);margin-bottom:6px}

.rv-key-points{font-size:14px;line-height:1.6;color:var(--fg-secondary);white-space:pre-wrap}

.rv-reveal-btn{width:100%;padding:14px;border:2px dashed var(--primary);border-radius:var(--radius-md);background:transparent;color:var(--primary);font-size:14px;cursor:pointer;font-family:inherit;font-weight:500;transition:all .15s;margin-top:auto}

.rv-reveal-btn:hover{background:var(--primary-light)}

.rv-rating{display:flex;gap:6px;align-items:center;margin-top:16px;flex-wrap:wrap}

.rv-rating-label{font-size:13px;color:var(--fg-secondary);margin-right:4px}

.rv-rate{padding:8px 16px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg);color:var(--fg);cursor:pointer;font-size:13px;font-family:inherit;transition:all .12s}

.rv-rate:hover{background:var(--bg-tertiary);border-color:var(--primary)}

.rv-done{text-align:center;padding:80px 20px;color:var(--fg-muted)}.rv-done .icon{font-size:56px;margin-bottom:12px}

.rv-done h3{font-size:18px;font-weight:500;color:var(--success);margin-bottom:6px}
/* Plan view */
.plan-view{padding:24px;overflow-y:auto;max-width:1000px;margin:0 auto;width:100%;display:flex;flex-direction:column;flex:1;gap:16px}
.plan-header{display:flex;justify-content:space-between;align-items:flex-start}
.plan-header h2{font-size:20px;margin-bottom:2px}
.plan-today{background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-md);padding:20px}
.plan-card-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.plan-card{background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-md);padding:18px;display:flex;flex-direction:column;gap:8px;position:relative}
.plan-card-name{font-size:15px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.plan-card-meta{font-size:12px;color:var(--fg-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.plan-card-progress{height:6px;background:var(--bg-tertiary);border-radius:3px;overflow:hidden}
.plan-card-progress .fill{height:100%;background:var(--primary);border-radius:3px;transition:width .3s}
.plan-card-progress .fill.done{background:var(--success)}
.plan-card-stats{font-size:12px;color:var(--fg-secondary);display:flex;gap:16px}
.plan-card-stats span{display:flex;align-items:center;gap:4px}
.plan-card-actions{display:flex;gap:6px;margin-top:auto;padding-top:4px}
.plan-card-actions button{font-size:12px;padding:5px 10px;border-radius:var(--radius-sm);border:none;cursor:pointer;font-family:inherit;transition:all .12s}
.plan-card-actions .practice-btn{background:var(--primary);color:#fff}
.plan-card-actions .practice-btn:hover{background:var(--primary-hover)}
.plan-card-actions .delete-btn{background:transparent;color:var(--danger);font-size:14px}
.plan-card-actions .delete-btn:hover{color:var(--danger);background:rgba(239,68,68,0.08)}
.plan-empty{text-align:center;padding:60px 20px;color:var(--fg-muted)}
.pv-plan-indicator{background:var(--primary-light);border:1px solid var(--primary);border-radius:var(--radius-md);padding:10px;margin-bottom:12px}
.pv-plan-list{display:flex;flex-direction:column;gap:8px}
/* Responsive */
@media(max-width:900px){.sidebar.collapsed{margin-left:calc(var(--sidebar-w)*-1)}.sidebar:not(.collapsed){position:fixed;left:0;top:0;bottom:0;z-index:100;box-shadow:var(--shadow-lg)}
.main{z-index:1}.topbar .menu-btn{display:block}
.sidebar-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:99;display:none}
.sidebar-overlay.active{display:block}
.sidebar:not(.collapsed)+.sidebar-overlay{display:block}}
@media(max-width:640px){.chat-inner{padding:0 12px}.input-area{padding:8px 12px 12px}.msg{max-width:92%;font-size:14px;padding:8px 14px}
.banks-view,.progress-view,.settings-view{padding:16px}.stats-grid{grid-template-columns:repeat(2,1fr)}
.topbar{padding:0 12px;height:48px}}
.hljs{background:transparent!important;padding:12px 16px!important}
pre code.hljs{padding:0!important}
.chip-group{display:flex;flex-wrap:wrap;gap:6px}
.plan-input{width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--bg);color:var(--fg);font-size:14px;font-family:inherit;box-sizing:border-box}
.plan-input:focus{outline:none;border-color:var(--primary)}
.rv-card-front,.rv-card-back{position:absolute;inset:0;-webkit-backface-visibility:hidden;backface-visibility:hidden;display:flex;flex-direction:column;justify-content:center;align-items:center;padding:20px;border-radius:var(--radius-lg);box-shadow:var(--shadow-md);font-size:18px;line-height:1.6}
.rv-card-front{background:var(--bg)}
.rv-card-back{background:var(--primary-light);transform:rotateY(180deg)}
button.primary{color:var(--primary);border-color:var(--primary);background:transparent;border:1px solid;padding:6px 14px;border-radius:var(--radius-sm);cursor:pointer;font-family:inherit;transition:all .12s}
button.primary:hover{background:var(--primary-light)}
</style>
</head>
<body>
<div class="app">
  <!-- Sidebar -->
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-header">
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
      <div><h1>Studybot</h1><span class="sub">智能备考助手</span></div>
    </div>
    <nav class="sidebar-nav">
      <button class="nav-item active" data-view="chat"><span class="nav-icon">💬</span> 对话</button>
      <button class="nav-item" data-view="banks"><span class="nav-icon">📚</span> 题库 <span class="badge" id="bankCount">0</span></button>
      <button class="nav-item" data-view="progress"><span class="nav-icon">📊</span> 学习进度</button>
      <button class="nav-item" data-view="practice"><span class="nav-icon">📝</span> 做题</button>
      <button class="nav-item" data-view="review"><span class="nav-icon">🧠</span> 背题 <span class="badge" id="reviewDue">0</span></button>
      <button class="nav-item" data-view="plan"><span class="nav-icon">📋</span> 学习计划</button>
      <div class="nav-section-title">系统</div>
      <button class="nav-item" data-view="settings"><span class="nav-icon">⚙️</span> 设置</button>
    </nav>
    <div class="sidebar-footer" style="flex-direction:column;gap:6px">
      <div style="font-size:10px;color:var(--fg-muted);line-height:1.3;text-align:center;width:100%">Studybot v1.0 · AI 智能做题</div>
      <div style="display:flex;align-items:center;gap:6px;width:100%">
        <span class="dot offline" id="siderDot"></span>
        <span class="s-label" id="siderLabel">未连接</span>
      </div>
    </div>
  </aside>
  <div class="sidebar-overlay" id="sidebarOverlay"></div>

  <!-- Main -->
  <div class="main">
    <div class="topbar">
      <button class="menu-btn" id="menuBtn">☰</button>
      <span class="topbar-title" id="topbarTitle">💬 对话</span>
      <div class="topbar-actions">
        <button class="theme-btn" id="themeBtn">🌙</button>
      </div>
    </div>
    <div class="views">
      <!-- Chat view -->
      <div class="view active" id="view-chat">
        <div class="chat" id="chat">
          <div class="chat-inner" id="chatInner">
            <div class="empty-state">
              <div class="icon">📝</div>
              <h3>有什么想练习的？</h3>
              <p>发送题目或上传文档，AI 会帮你生成练习题目</p>
            </div>
          </div>
        </div>
        <div class="input-area">
          <div class="input-inner">
            <div class="input-actions">
              <button class="action-btn" id="uploadBtn" title="上传文档">📎</button>
              <input type="file" id="fileInput" multiple accept=".txt,.md,.pdf,.csv,.json,.xml,.yaml">
            </div>
            <textarea id="input" placeholder="输入消息..." rows="1"></textarea>
            <button class="action-btn send-btn" id="sendBtn">➤</button>
          </div>
        </div>
      </div>

      <!-- Banks view -->
      <div class="view" id="view-banks">
        <div class="banks-view">
          <h2>📚 题库管理</h2>
          <p class="subtitle">管理已上传的题库，查看题目数量和覆盖领域</p>
          <div style="margin-bottom:16px">
            <button class="save-btn" id="uploadBankBtn">+ 上传新题库</button>
            <input type="file" id="bankFileInput" multiple accept=".txt,.md,.pdf,.csv,.json,.xml,.yaml" style="display:none">
          </div>
          <div id="banksList"><div class="banks-empty"><div class="icon">📂</div><p>暂无题库，上传文档开始练习</p></div></div>
        </div>
      </div>

      <!-- Progress view -->
      <div class="view" id="view-progress">
        <div class="progress-view">
          <h2>📊 学习进度</h2>
          <p class="subtitle">查看练习统计和领域分布</p>
          <div class="stats-grid">
            <div class="stat-card"><div class="stat-icon">📝</div><div class="stat-value" id="totalQ">0</div><div class="stat-label">练习题目</div></div>
            <div class="stat-card"><div class="stat-icon">✅</div><div class="stat-value" id="accuracy">0%</div><div class="stat-label">正确率</div></div>
            <div class="stat-card"><div class="stat-icon">📚</div><div class="stat-value" id="statBankCount">0</div><div class="stat-label">题库数量</div></div>
            <div class="stat-card"><div class="stat-icon">📈</div><div class="stat-value" id="streakDays">0</div><div class="stat-label">连续天数</div></div>
          </div>
          <div class="progress-section">
            <h3>题库分布</h3>
            <div id="bankBars"><p style="color:var(--fg-muted);font-size:13px">暂无数据，上传题库后这里会显示题目分布</p></div>
          </div>
          <div class="progress-section" style="margin-top:24px">
            <h3>最近活动</h3>
            <ul class="activity-list" id="activityList"><li style="color:var(--fg-muted);font-size:13px;padding:8px 0">暂无活动记录</li></ul>
          </div>
        </div>
      </div>

      <!-- Practice view -->
      <div class="view" id="view-practice">
        <div class="practice-view">
          <!-- Mode selector -->
          <div id="pvModeSelector" class="pv-mode-selector">
            <h2>📝 请选择做题模式</h2>
            <div class="pv-mode-cards">
              <div class="pv-mode-card" onclick="setPracticeMode('bank')">
                <div class="pv-mode-icon">📚</div>
                <div class="pv-mode-title">按题库做题</div>
                <div class="pv-mode-desc">选择题库和难度，自由刷题练习</div>
              </div>
              <div class="pv-mode-card" onclick="setPracticeMode('plan')">
                <div class="pv-mode-icon">📋</div>
                <div class="pv-mode-title">按学习计划做题</div>
                <div class="pv-mode-desc">根据已创建的学习计划进行针对性练习</div>
              </div>
            </div>
          </div>
          <!-- Practice content -->
          <div id="pvContent" class="pv-content" style="display:none">
            <div class="pv-main">
              <div class="pv-header">
                <button class="pv-back-btn" id="pvBackBtn" title="返回选择模式">←</button>
                <div>
                  <h2>📝 <span id="pvTitle">做题练习</span></h2>
                  <p id="pvDomain"></p>
                </div>
              </div>
              <div class="pv-question" id="pvQuestion" style="display:none">
                <div class="pv-q-text" id="pvQText"></div>
              </div>
              <div class="pv-answer">
                <textarea id="pvAnswer" placeholder="输入你的答案..." rows="8"></textarea>
              </div>
              <div class="pv-actions">
                <button class="save-btn" id="pvSubmitBtn">提交答案</button>
                <button class="save-btn" id="pvAddReviewBtn" style="display:none;background:var(--success)">📥 加入背题</button>
                <button class="save-btn" id="pvNextBtn" style="display:none">下一题</button>
              </div>
              <div class="pv-eval" id="pvEval" style="display:none">
                <div class="pv-eval-score" id="pvEvalScore"></div>
                <div class="pv-eval-feedback" id="pvEvalFeedback"></div>
                <div class="pv-eval-missing" id="pvEvalMissing"></div>
              </div>
            </div>
            <div class="pv-sidebar">
              <!-- Bank mode controls -->
              <div id="pvBankControls" class="pv-controls">
                <button class="save-btn" id="pvStartBtn" style="width:100%">🎯 生成题目</button>
                <div class="pv-filter-group">
                  <label>📚 题库（多选）</label>
                  <div class="pv-chips" id="pvBankChips">
                    <button class="chip active" data-value="">全部题库</button>
                  </div>
                </div>
                <div class="pv-filter-group">
                  <label>📊 难度（多选）</label>
                  <div class="pv-chips" id="pvDiffChips">
                    <button class="chip active" data-value="简单">简单</button>
                    <button class="chip active" data-value="中等">中等</button>
                    <button class="chip active" data-value="困难">困难</button>
                  </div>
                </div>
              </div>
              <!-- Plan mode controls -->
              <div id="pvPlanControls" class="pv-controls" style="display:none">
                <div id="pvPlanIndicator" class="pv-plan-indicator" style="display:none">
                  <div style="font-size:12px;font-weight:600;margin-bottom:4px">📋 当前计划</div>
                  <div id="pvPlanInfo" style="font-size:12px;color:var(--fg-secondary);margin-bottom:6px"></div>
                  <button id="pvPlanStopBtn" style="font-size:11px;padding:4px 10px;border:none;background:var(--bg-tertiary);color:var(--fg-muted);border-radius:var(--radius-sm);cursor:pointer;font-family:inherit">✕ 退出计划</button>
                </div>
                <button class="save-btn" id="pvPlanNextBtn" style="width:100%">➡ 下一题</button>
                <div id="pvPlanList" class="pv-plan-list"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Review view -->
      <div class="view" id="view-review">
        <div class="review-view">
          <div class="rv-header">
            <h2>🧠 背题复习</h2>
            <p class="subtitle" id="rvSubtitle">今日待复习: 0 题</p>
          </div>
          <div class="rv-empty" id="rvEmpty">
            <div class="icon">🎉</div>
            <h3>暂无待复习题目</h3>
            <p>做题后把题目加入背题列表即可开始复习</p>
          </div>
          <div class="rv-card" id="rvCard" style="display:none">
            <div class="rv-domain-tag" id="rvDomain"></div>
            <div class="rv-card-front">
              <div class="rv-label">题目</div>
              <div class="rv-question" id="rvQuestion"></div>
            </div>
            <div class="rv-card-back" id="rvBack" style="display:none">
              <div class="rv-divider"></div>
              <div class="rv-label">答案</div>
              <div class="rv-answer" id="rvAnswer"></div>
              <div class="rv-key-points-label">📌 记忆重点</div>
              <div class="rv-key-points" id="rvKeyPoints"></div>
            </div>
            <button class="rv-reveal-btn" id="rvRevealBtn">👆 点击显示答案</button>
            <div class="rv-rating" id="rvRating" style="display:none">
              <div class="rv-rating-label">回忆效果：</div>
              <button class="rv-rate" data-quality="1">😰 忘了</button>
              <button class="rv-rate" data-quality="2">🤔 困难</button>
              <button class="rv-rate" data-quality="3">😊 一般</button>
              <button class="rv-rate" data-quality="4">👍 简单</button>
            </div>
          </div>
          <div class="rv-done" id="rvDone" style="display:none">
            <div class="icon">✅</div>
            <h3>本轮复习完成!</h3>
            <p id="rvDoneMsg"></p>
          </div>
        </div>
      </div>

      <!-- Settings view -->
      <div class="view" id="view-settings">
        <div class="settings-view">
          <h2>⚙️ 设置</h2>
          <p class="subtitle">配置 AI 提供商、通道和其他偏好</p>

          <div class="settings-group">
            <h3>AI 提供商</h3>
            <div class="setting-row"><div><div class="s-label">API Key</div><div class="s-hint">OpenAI 兼容密钥</div></div><input type="password" id="apiKey" placeholder="sk-..." style="width:220px"></div>
            <div class="setting-row"><div><div class="s-label">API Base URL</div><div class="s-hint">API 端点地址</div></div><input type="text" id="apiBase" value="https://api.deepseek.com" style="width:220px"></div>
            <div class="setting-row"><div><div class="s-label">模型</div></div><input type="text" id="modelName" value="deepseek-v4-flash" style="width:160px"></div>
          </div>

          <div class="settings-group">
            <h3>飞书 通道</h3>
            <div class="setting-row"><div><div class="s-label">App ID</div><div class="s-hint">飞书开放平台应用的 App ID</div></div><input type="text" id="feishuAppId" placeholder="cli_..." style="width:220px"></div>
            <div class="setting-row"><div><div class="s-label">App Secret</div><div class="s-hint">飞书开放平台应用的 App Secret</div></div><input type="password" id="feishuAppSecret" placeholder="请输入" style="width:220px"></div>
          </div>

          <div class="settings-group">
            <h3>界面</h3>
            <div class="setting-row"><div><div class="s-label">主题</div></div><select id="themeSelect"><option value="auto">跟随系统</option><option value="light">亮色</option><option value="dark">暗色</option></select></div>
          </div>

          <div style="display:flex;gap:8px;align-items:center;margin-bottom:20px">
            <button class="save-btn" id="saveSettingsBtn">💾 保存设置</button>
            <span id="settingsStatus" style="font-size:13px;color:var(--fg-muted)"></span>
          </div>

        </div>
      </div>
      <!-- Plan view -->
      <div class="view" id="view-plan">
        <div class="plan-view">
          <div class="plan-header">
            <div>
              <h2>📋 学习计划</h2>
              <p class="subtitle">根据题库和天数制定做题计划</p>
            </div>
            <button class="save-btn" id="planNewBtn">+ 新建计划</button>
          </div>

          <div class="plan-today" id="planToday">
            <h3 style="margin:0 0 10px 0">📌 今日任务</h3>
            <div id="planTodayContent">
              <p style="color:var(--fg-muted);text-align:center;padding:20px 0">暂无活跃计划</p>
            </div>
          </div>

          <div id="planList">
            <div id="planListContent"></div>
          </div>
        </div>
      </div>

      <!-- Plan create modal -->
      <div class="qmodal" id="planModal">
        <div class="qmodal-box" style="max-width:520px">
          <div class="qmodal-header">
            <h3>📝 新建计划</h3>
            <button class="qmodal-close" id="planModalClose">&times;</button>
          </div>
          <div class="qmodal-body">
            <div style="display:flex;flex-direction:column;gap:12px">
              <input type="text" id="planName" placeholder="计划名称（如：考公复习）" class="plan-input" style="width:100%;padding:10px 12px">
              <div>
                <label style="font-size:13px;font-weight:500;display:block;margin-bottom:6px">选择题库：</label>
                <div id="planBanksList" class="chip-group"></div>
              </div>
              <div id="planBankStats" style="font-size:13px;color:var(--fg-secondary);display:none"></div>
              <div style="display:flex;gap:16px;align-items:center">
                <div>
                  <label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">总天数</label>
                  <input type="number" id="planDays" value="30" min="1" max="365" class="plan-input" style="width:80px;padding:8px 10px">
                </div>
                <div>
                  <label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">每日题数</label>
                  <input type="number" id="planQpd" value="10" min="1" max="500" class="plan-input" style="width:80px;padding:8px 10px">
                </div>
                <div style="font-size:13px;color:var(--fg-muted);padding-top:16px">共 <span id="planTotalQ">0</span> 题</div>
              </div>
              <button class="save-btn" id="createPlanBtn" style="width:100%;margin-top:4px">✅ 创建计划</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>
<div class="drag-overlay"><div class="drag-overlay-inner">📄 释放文件以上传</div></div>
<div class="upload-loading" id="uploadLoading">
  <div class="upload-loading-box">
    <div class="upload-spinner"></div>
    <div class="upload-status" id="uploadStatus">正在上传...</div>
    <div class="upload-sub" id="uploadSub">正在解析文件内容</div>
  </div>
</div>
<div class="qmodal" id="qmodal">
  <div class="qmodal-box">
    <div class="qmodal-header">
      <h3 id="qmodalTitle">题目列表</h3>
      <button class="qmodal-close" id="qmodalClose">&times;</button>
    </div>
    <div class="qmodal-body" id="qmodalBody"></div>
  </div>
</div>

<script>
const WS_URL = 'ws://HOST:PORT';
const markedOptions = {breaks:true,gfm:true};
let ws=null,streamContent='',streamMsgEl=null,isStreaming=false,fileList=[];


const $=id=>document.getElementById(id);
const chat=$('chat'),chatInner=$('chatInner'),input=$('input'),sendBtn=$('sendBtn');
const uploadBtn=$('uploadBtn'),fileInput=$('fileInput'),menuBtn=$('menuBtn');
const sidebar=$('sidebar'),sidebarOverlay=$('sidebarOverlay'),topbarTitle=$('topbarTitle');
const themeBtn=$('themeBtn'),siderDot=$('siderDot'),siderLabel=$('siderLabel');
const toast=$('toast');

/* Theme */
function applyTheme(dark){
  document.documentElement.classList.toggle('dark',dark);
  themeBtn.textContent=dark?'☀️':'🌙';
  localStorage.setItem('studybot-theme',dark?'dark':'light');
  const sel=$('themeSelect');
  if(sel)sel.value=dark?'dark':'light'
}
function setThemeMode(mode){
  if(mode==='auto'){
    const dark=window.matchMedia('(prefers-color-scheme:dark)').matches;
    document.documentElement.classList.toggle('dark',dark);
    themeBtn.textContent=dark?'☀️':'🌙';
    localStorage.setItem('studybot-theme','auto');
  }else{
    applyTheme(mode==='dark')
  }
  if($('themeSelect'))$('themeSelect').value=mode
}
function loadTheme(){
  const t=localStorage.getItem('studybot-theme');
  setThemeMode(t||'auto');
  if($('themeSelect'))$('themeSelect').value=t||'auto'
}
themeBtn.onclick=()=>{
  const dark=!document.documentElement.classList.contains('dark');
  applyTheme(dark);
  if($('themeSelect'))$('themeSelect').value=dark?'dark':'light'
};
window.matchMedia('(prefers-color-scheme:dark)').addEventListener('change',e=>{
  if(localStorage.getItem('studybot-theme')==='auto'||!localStorage.getItem('studybot-theme')){
    document.documentElement.classList.toggle('dark',e.matches);
    themeBtn.textContent=e.matches?'☀️':'🌙'
  }
});
$('themeSelect')&&($('themeSelect').onchange=function(){setThemeMode(this.value)});
loadTheme();

/* Sidebar nav */
document.querySelectorAll('.nav-item').forEach(item=>{
  item.onclick=()=>{
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
    item.classList.add('active');
    const view=item.dataset.view;
    document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
    const el=$('view-'+view);
    if(el)el.classList.add('active');
    topbarTitle.textContent=item.textContent.trim();
    if(window.innerWidth<900)toggleSidebar(false)
    if(view==='banks')fetchBanks();
    if(view==='progress')fetchStats();
    if(view==='settings')loadSettings();
    if(view==='review')loadReviewCards();
    if(view==='plan')fetchPlans();
    if(view==='practice'){
      if(window._activePlan&&window._activePlan.id){
        $('pvModeSelector').style.display='none';
        $('pvContent').style.display='';
        const plan=planData.plans.find(p=>p.id===window._activePlan.id);
        $('pvTitle').textContent='📋 '+(plan?plan.name:'计划');
        $('pvBankControls').style.display='none';
        $('pvPlanControls').style.display='';
        refreshPlanIndicator()
      }else if(pvMode==='bank'){
        $('pvModeSelector').style.display='none';
        $('pvContent').style.display='';
        $('pvTitle').textContent='按题库做题';
        $('pvBankControls').style.display='';
        $('pvPlanControls').style.display='none'
      }else if(pvMode==='plan'){
        $('pvModeSelector').style.display='none';
        $('pvContent').style.display='';
        $('pvTitle').textContent='按计划做题';
        $('pvBankControls').style.display='none';
        $('pvPlanControls').style.display='';
        renderPvPlanList()
      }else{
        $('pvModeSelector').style.display='';
        $('pvContent').style.display='none';
        delete window._activePlan;
      }
    }
  }
});
function toggleSidebar(open){
  if(open)sidebar.classList.remove('collapsed')
  else if(open===false)sidebar.classList.add('collapsed')
  else sidebar.classList.toggle('collapsed')
  sidebarOverlay.classList.toggle('active',!sidebar.classList.contains('collapsed'))
}
menuBtn.onclick=()=>{toggleSidebar()};
sidebarOverlay.onclick=()=>{toggleSidebar(false)};
window.addEventListener('resize',()=>{
  const w=window.innerWidth,prevWidth=window._lastWidth||w;
  if(prevWidth<900&&w>=900)sidebar.classList.remove('collapsed');
  window._lastWidth=w
});

/* Settings */
function loadSettings(){
  fetch('/api/settings').then(r=>r.json()).then(d=>{
    if(d.api_key)$('apiKey').value=d.api_key;
    if(d.api_base)$('apiBase').value=d.api_base;
    if(d.model)$('modelName').value=d.model;
  }).catch(()=>{})
}
function saveSettings(){
  const btn=$('saveSettingsBtn'),status=$('settingsStatus');
  btn.disabled=true;status.textContent='保存中...';
  fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    api_key:$('apiKey').value,api_base:$('apiBase').value,model:$('modelName').value,
    feishu_app_id:$('feishuAppId').value,feishu_app_secret:$('feishuAppSecret').value,
  })}).then(r=>r.json()).then(d=>{
    btn.disabled=false;
    if(d.ok){
      let msg=d.restart_required?d.restart_required.join('、')+' 配置已保存，重启后生效':'已保存';
      status.textContent='✅ '+msg;status.style.color='var(--success)';
    }else{status.textContent='❌ 保存失败';status.style.color='var(--danger)'}
  }).catch(()=>{btn.disabled=false;status.textContent='❌ 网络错误';status.style.color='var(--danger)'})
}
$('saveSettingsBtn')&&($('saveSettingsBtn').onclick=saveSettings);

/* Practice view */
let pvQuestionData=null,pvEvalData=null,practiceBanks=[];
let pvMode=null; // 'bank' or 'plan'

function setPracticeMode(mode){
  pvMode=mode;
  $('pvModeSelector').style.display='none';
  $('pvContent').style.display='';
  if(mode==='bank'){
    $('pvTitle').textContent='按题库做题';
    $('pvBankControls').style.display='';
    $('pvPlanControls').style.display='none';
    delete window._activePlan;
    refreshPracticeControls();
    refreshPlanIndicator()
  }else{
    $('pvTitle').textContent='按计划做题';
    $('pvBankControls').style.display='none';
    $('pvPlanControls').style.display='';
    renderPvPlanList()
  }
}
$('pvBackBtn')&&($('pvBackBtn').onclick=()=>{
  pvMode=null;
  $('pvModeSelector').style.display='';
  $('pvContent').style.display='none';
  delete window._activePlan
});
function renderPvPlanList(){
  const el=$('pvPlanList');
  if(!el)return;
  fetch('/api/plans').then(r=>r.json()).then(d=>{
    const plans=d.plans||[];
    if(!plans.length){el.innerHTML='<p style="color:var(--fg-muted);font-size:13px;text-align:center;padding:20px 0">暂无计划，先去学习计划页面创建</p>';return}
    el.innerHTML=plans.map(p=>{
      const day=getPlanDay(p);
      const todayStr=new Date().toISOString().slice(0,10);
      const log=p.logs[day];
      const doneCount=log&&log.date===todayStr?log.completed:0;
      const remaining=p.questions_per_day-doneCount;
      return `<div style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-md);padding:12px;cursor:pointer" onclick="startPlanPractice('${p.id}')">
        <div style="font-size:14px;font-weight:600;margin-bottom:4px">${escapeHtml(p.name)}</div>
        <div style="font-size:12px;color:var(--fg-secondary)">第${Math.min(day,p.total_days)}/${p.total_days}天 · ${doneCount}/${p.questions_per_day} 题${remaining>0?' · 剩余'+remaining+'题':''}</div>
      </div>`
    }).join('')
  }).catch(()=>{})
}

function refreshPlanIndicator(){
  const el=$('pvPlanIndicator'),info=$('pvPlanInfo');
  if(window._activePlan&&planData.plans){
    const plan=planData.plans.find(p=>p.id===window._activePlan.id);
    if(plan){
      const day=window._activePlan.day;
      el.style.display='';
      info.textContent=`${plan.name} · 第${day}天 (已完成 ${window._activePlan.completed}/${window._activePlan.total})`;
      return
    }
  }
  el.style.display='none'
}
$('pvPlanStopBtn')&&($('pvPlanStopBtn').onclick=function(){
  delete window._activePlan;
  refreshPlanIndicator();
  $('pvTitle').textContent='按计划做题';
  pvMode='plan';
  $('pvBankControls').style.display='none';
  $('pvPlanControls').style.display='';
  renderPvPlanList()
});

function getActiveChips(containerId){
  return Array.from($(containerId).querySelectorAll('.chip.active'))
    .map(c=>c.dataset.value).filter(v=>v!=='')
}

function chipClickHandler(e){
  const chip=e.currentTarget;const group=chip.parentElement;const isAll=chip.dataset.value==='';
  if(isAll){
    group.querySelectorAll('.chip').forEach(c=>c.classList.toggle('active',c===chip))
  }else{
    chip.classList.toggle('active');
    const hasSpecific=group.querySelectorAll('.chip:not([data-value=""]).active').length>0;
    const allChip=group.querySelector('.chip[data-value=""]');
    if(allChip)allChip.classList.toggle('active',!hasSpecific)
  }
  savePracticeSelections()
}

function savePracticeSelections(){
  localStorage.setItem('practice-selections',JSON.stringify({
    banks:getActiveChips('pvBankChips'),
    diffs:getActiveChips('pvDiffChips')
  }))
}

function restorePracticeSelections(){
  try{
    const raw=localStorage.getItem('practice-selections');
    if(!raw)return;
    const data=JSON.parse(raw);
    ['pvBankChips','pvDiffChips'].forEach(id=>{
      const container=$(id);if(!container)return;
      const vals=data[id==='pvBankChips'?'banks':'diffs']||[];
      container.querySelectorAll('.chip').forEach(c=>{
        c.classList.toggle('active',vals.includes(c.dataset.value))
      });
      if(!container.querySelector('.chip.active')){
        const sentinel=container.querySelector('.chip');
        if(sentinel)sentinel.classList.add('active')
      }
    })
  }catch(e){}
}

$('pvStartBtn').onclick=loadPracticeQuestion;
$('pvPlanNextBtn')&&($('pvPlanNextBtn').onclick=loadPracticeQuestion);
async function loadPracticeQuestion(){
  let banks=getActiveChips('pvBankChips'),diffs=getActiveChips('pvDiffChips');
  $('pvDomain').textContent='生成中...';
  $('pvQuestion').style.display='none';$('pvEval').style.display='none';$('pvEval').className='pv-eval';
  $('pvSubmitBtn').style.display='';$('pvAddReviewBtn').style.display='none';$('pvNextBtn').style.display='none';
  try{
    let d;
    // Plan mode: use pre-assigned questions
    if(window._activePlan&&window._activePlan.id){
      const plan=planData.plans.find(p=>p.id===window._activePlan.id);
      if(!plan||!plan.questions||!plan.questions.length){$('pvDomain').textContent='计划暂无题目';return}
      const idx=(window._activePlan.day-1)*plan.questions_per_day+window._activePlan.currentIndex;
      const q=plan.questions[idx];
      if(!q){$('pvDomain').textContent='今日题目已用完';return}
      d={question:q.question,expected_answer:q.expected_answer,key_points:q.key_points||[],bank_name:q.bank_name||'',difficulty:''}
    }else{
      // Bank mode: generate via API
      const r=await fetch('/api/practice/question',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bank_names:banks,difficulties:diffs})});
      d=await r.json();
      if(d.error){$('pvDomain').textContent='出题失败: '+d.error;return}
    }
    pvQuestionData=d;pvEvalData=null;
    $('pvQText').textContent=d.question||'';
    if(window._activePlan&&window._activePlan.id){
      const p=planData.plans.find(x=>x.id===window._activePlan.id);
      const total=window._activePlan.total;
      const cur=window._activePlan.currentIndex;
      $('pvDomain').textContent='📋 '+(p?p.name:'计划')+' · '+(cur+1)+'/'+total+' 题'
    }else{
      $('pvDomain').textContent='📌 '+(banks.length?banks.join('+'):'全部题库')+' · '+(diffs.length?diffs.join('+'):'全部难度')
    }
    $('pvQuestion').style.display='block';
    $('pvAnswer').value='';
  }catch(e){$('pvDomain').textContent='网络错误: '+e.message}
}
$('pvSubmitBtn').onclick=async function(){
  const answer=$('pvAnswer').value.trim();
  if(!answer||!pvQuestionData)return;
  $('pvSubmitBtn').disabled=true;$('pvSubmitBtn').textContent='评价中...';
  try{
    const r=await fetch('/api/practice/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answer})});
    const d=await r.json();
    if(d.error){alert('提交失败: '+d.error);return}
    pvEvalData=d;
    const el=$('pvEval');el.className='pv-eval '+(d.correct?'good':'bad');
    const score=Math.round(d.score||0);
    $('pvEvalScore').textContent=d.correct?'✅ '+score+'分 回答正确!':'❌ '+score+'分 回答有误';
    $('pvEvalScore').style.color=d.correct?'var(--success)':'var(--danger)';
    $('pvEvalFeedback').textContent=d.feedback||'';
    $('pvEvalMissing').textContent=(d.missing_points||[]).join('、');
    el.style.display='block';
    $('pvSubmitBtn').style.display='none';
    $('pvAddReviewBtn').style.display='';$('pvNextBtn').style.display='';
    // Track plan progress
    if(window._activePlan){
      const ap=window._activePlan;
      ap.completed++;
      ap.currentIndex++;
      const plan=planData.plans.find(p=>p.id===ap.id);
      if(plan){
        const log=plan.logs[ap.day]||{date:ap.date,completed:0,total:ap.total};
        log.completed=ap.completed;
        plan.logs[ap.day]=log;
        // Persist to backend
        fetch('/api/plans/progress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:ap.id,logs:plan.logs})}).catch(()=>{})
      }
      if(ap.completed>=ap.total)delete window._activePlan
    }
  }catch(e){alert('网络错误')}
  finally{$('pvSubmitBtn').disabled=false;$('pvSubmitBtn').textContent='提交答案'}
};
$('pvAddReviewBtn').onclick=async function(){
  if(!pvQuestionData)return;
  try{
    const r=await fetch('/api/review/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      question:pvQuestionData.question||'',answer:pvQuestionData.expected_answer||'',
      key_points:(pvQuestionData.key_points||[]).join('\n'),domain:pvQuestionData.domain||''
    })});
    const d=await r.json();
    if(d.ok){
      $('pvAddReviewBtn').textContent='✅ 已加入';$('pvAddReviewBtn').disabled=true;
      if(d.stats){$('reviewDue').textContent=d.stats.due||0}
    } else showToast('❌ 加入失败')
  }catch(e){showToast('❌ 网络错误')}
};
$('pvNextBtn').onclick=loadPracticeQuestion;

/* Review view */
let rvCards=[],rvIdx=0;
async function loadReviewCards(){
  try{
    const r=await fetch('/api/review/due');const d=await r.json();
    const due=d.stats?.due||0,total=d.stats?.total||0;
    $('reviewDue').textContent=due;
    $('rvSubtitle').textContent=due?'今日待复习: '+due+' 题':'暂无待复习 ('+total+' 张卡片)';
    rvCards=d.cards||[];rvIdx=0;
    $('rvEmpty').style.display=rvCards.length?'none':'';
    $('rvCard').style.display=rvCards.length?'':'none';
    $('rvDone').style.display='none';
    if(rvCards.length)showReviewCard(0)
  }catch(e){}
}
function showReviewCard(idx){
  if(idx>=rvCards.length){$('rvCard').style.display='none';$('rvDone').style.display='';$('rvDoneMsg').textContent='共复习了 '+rvCards.length+' 题';return}
  const c=rvCards[idx];rvIdx=idx;
  $('rvDomain').textContent=c.domain||'综合';
  $('rvQuestion').textContent=c.question||'';
   $('rvAnswer').textContent=c.answer||'(无预设答案)';
  $('rvKeyPoints').textContent=c.key_points||'';
  $('rvBack').style.display='none';
  $('rvRevealBtn').style.display='';
  $('rvRating').style.display='none';
  $('rvCard').style.display=''
}
$('rvRevealBtn').onclick=()=>{
  $('rvBack').style.display='';
  $('rvRevealBtn').style.display='none';
  $('rvRating').style.display='flex'
};
document.querySelectorAll('.rv-rate').forEach(btn=>{
  btn.onclick=async function(){
    const c=rvCards[rvIdx];if(!c)return;
    const q=parseInt(this.dataset.quality);
    try{
      await fetch('/api/review/rate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:c.id,quality:q})})
    }catch(e){}
    showReviewCard(rvIdx+1)
  }
});

/* Plan */
let planData={plans:[],banks:[]};
async function fetchPlans(){
  try{
    const r=await fetch('/api/plans');const d=await r.json();
    planData.plans=d.plans||[];
    const br=await fetch('/api/banks');const bd=await br.json();
    planData.banks=bd.banks||[];
    renderPlanList();renderPlanToday();refreshPlanIndicator()
  }catch(e){}
}
function renderPlanList(){
  const el=$('planListContent');
  if(!planData.plans.length){el.innerHTML='<div class="plan-empty">📋 还没有学习计划<br><span style="font-size:13px;color:var(--fg-muted)">点击右上角「+ 新建计划」开始</span></div>';return}
  el.innerHTML='<div class="plan-card-grid">'+planData.plans.map(p=>{
    const day=getPlanDay(p);
    const totalQ=p.questions?p.questions.length:p.total_days*p.questions_per_day;
    let completedQ=0;
    Object.values(p.logs||{}).forEach(l=>{completedQ+=l.completed||0});
    const pct=Math.min(completedQ/totalQ*100,100);
    const doneToday=p.logs[day]&&p.logs[day].date===new Date().toISOString().slice(0,10);
    return `<div class="plan-card">
      <div class="plan-card-name">${escapeHtml(p.name)}</div>
      <div class="plan-card-meta">${p.bank_names.length}个题库 · 第${Math.min(day,p.total_days)}/${p.total_days}天</div>
      <div class="plan-card-progress"><div class="fill ${pct>=100?'done':''}" style="width:${pct}%"></div></div>
      <div class="plan-card-stats">
        <span>📝 ${completedQ}/${totalQ} 题</span>
        <span>📅 每日 ${p.questions_per_day} 题</span>
        <span>${doneToday?'✅ 今日已完成':''}</span>
      </div>
      <div class="plan-card-actions">
        <button class="practice-btn" onclick="startPlanPractice('${p.id}')">▶ 开始做题</button>
        <button class="delete-btn" onclick="deletePlan('${p.id}')">🗑</button>
      </div>
    </div>`
  }).join('')+'</div>'
}
function getPlanDay(plan){
  const start=new Date(plan.created);
  const diff=Math.floor((Date.now()-start.getTime())/(86400000));
  return Math.max(diff+1,1)
}
function renderPlanToday(){
  const el=$('planTodayContent');
  const active=planData.plans.filter(p=>getPlanDay(p)<=p.total_days);
  if(!active.length){el.innerHTML='<p style="color:var(--fg-muted);text-align:center;padding:20px 0">暂无活跃计划</p>';return}
  let html='';
  for(const p of active){
    const day=getPlanDay(p);
    const todayStr=new Date().toISOString().slice(0,10);
    const log=p.logs[day];
    const doneCount=log&&log.date===todayStr?log.completed:0;
    const remaining=p.questions_per_day-doneCount;
    html+=`<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)">
      <div style="flex:1;min-width:0">
        <div style="font-size:14px;font-weight:600">${escapeHtml(p.name)}</div>
        <div style="font-size:12px;color:var(--fg-secondary)">第${day}/${p.total_days}天 · ${doneCount}/${p.questions_per_day} 题</div>
      </div>
      ${remaining>0?`<button class="primary" style="flex-shrink:0;font-size:12px;padding:6px 14px" onclick="startPlanPractice('${p.id}')">📝 继续 (${remaining})</button>`
      :'<span style="color:var(--success);font-size:13px;flex-shrink:0">✅ 今日完成</span>'}
    </div>`
  }
  el.innerHTML=html
}
function refreshPlanForm(){
  const el=$('planBanksList'),stats=$('planBankStats');
  if(!el)return;
  fetch('/api/banks').then(r=>r.json()).then(d=>{
    const banks=d.banks||[];
    el.innerHTML='<button class="chip active" data-value="">全部题库</button>'+
      banks.map((b,i)=>`<button class="chip" data-value="${escapeHtml(b.name||'题库 '+i)}">${escapeHtml(b.name||'题库 '+(i+1))}</button>`).join('');
    el.querySelectorAll('.chip').forEach(c=>c.onclick=function(){
      const isAll=this.dataset.value==='';
      if(isAll){
        el.querySelectorAll('.chip').forEach(x=>x.classList.toggle('active',x===this))
      }else{
        this.classList.toggle('active');
        const hasSpecific=el.querySelectorAll('.chip:not([data-value=""]).active').length>0;
        const allChip=el.querySelector('.chip[data-value=""]');
        if(allChip)allChip.classList.toggle('active',!hasSpecific)
      }
      updatePlanBankStats()
    });
    updatePlanBankStats()
  })
}
function updatePlanBankStats(){
  const chips=$('planBanksList').querySelectorAll('.chip.active');
  const stats=$('planBankStats');
  if(!chips.length)return;
  const allSelected=chips.length===1&&chips[0].dataset.value==='';
  let bankNames=[];
  chips.forEach(c=>{if(c.dataset.value)bankNames.push(c.dataset.value)});
  let totalQ=0;
  planData.banks.forEach(b=>{
    if(allSelected||bankNames.includes(b.name||'')){
      totalQ+=(b._questions||b.questions||[]).length
    }
  });
  $('planTotalQ').textContent=totalQ;
  if(totalQ>0){
    stats.style.display='';
    stats.innerHTML=`已选 ${allSelected?'全部':bankNames.length+'个'} 题库，共 ${totalQ} 题`;
    const days=parseInt($('planDays').value)||1;
    $('planQpd').value=Math.max(1,Math.ceil(totalQ/days))
  }else{stats.style.display='none'}
}
$('planModal')&&($('planNewBtn').onclick=()=>{
  $('planModal').classList.add('active');
  refreshPlanForm()
});
$('planModalClose')&&($('planModalClose').onclick=()=>$('planModal').classList.remove('active'));
$('planModal')&&($('planModal').onclick=e=>{if(e.target===$('planModal'))$('planModal').classList.remove('active')});
$('planDays')&&($('planDays').oninput=()=>{const d=parseInt($('planDays').value)||1;const t=$('planTotalQ');const total=parseInt(t.textContent)||0;$('planQpd').value=Math.max(1,Math.ceil(total/d))});
$('createPlanBtn')&&($('createPlanBtn').onclick=async function(){
  const name=$('planName').value.trim();
  if(!name){alert('请输入计划名称');return}
  const days=parseInt($('planDays').value)||30;
  const qpd=parseInt($('planQpd').value)||10;
  const chips=$('planBanksList').querySelectorAll('.chip.active');
  let bankNames=[];
  chips.forEach(c=>{if(c.dataset.value)bankNames.push(c.dataset.value)});
  await fetch('/api/plans/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    name,bank_names:bankNames,total_days:days,questions_per_day:qpd
  })});
  $('planName').value='';
  $('planModal').classList.remove('active');
  fetchPlans()
});
async function deletePlan(id){
  if(!confirm('确定删除此计划？'))return;
  await fetch('/api/plans/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
  fetchPlans()
}
async function startPlanPractice(planId){
  const plan=planData.plans.find(p=>p.id===planId);
  if(!plan)return;
  const todayStr=new Date().toISOString().slice(0,10);
  const day=getPlanDay(plan);
  const log=plan.logs[day]||{date:todayStr,completed:0,total:plan.questions_per_day};
  // Always switch to practice view if not already there
  if(!document.getElementById('view-practice').classList.contains('active')){
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
    document.querySelector('[data-view="practice"]')?.classList.add('active');
    document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
    const pv=$('view-practice');
    if(pv)pv.classList.add('active');
    if(window.innerWidth<900)toggleSidebar(false)
  }
  pvMode='bank-plan';
  $('pvModeSelector').style.display='none';
  $('pvContent').style.display='';
  $('pvTitle').textContent='📋 '+plan.name;
  $('pvBankControls').style.display='none';
  $('pvPlanControls').style.display='';
  window._activePlan={id:planId,day,date:todayStr,completed:log.completed,total:plan.questions_per_day,currentIndex:0};
  refreshPlanIndicator();
  if(log.completed<plan.questions_per_day)setTimeout(loadPracticeQuestion,100)
}

async function fetchBanks(){
  try{
    const r=await fetch('/api/banks');const d=await r.json();
    const list=$('banksList'),badge=$('bankCount');
    if(d.banks&&d.banks.length){
      badge.textContent=d.banks.length;
      list.innerHTML=d.banks.map((b,i)=>`<div class="bank-card">
        <div class="bank-name">${escapeHtml(b.name||'未命名')} <span class="bank-count">${b._questions?b._questions.length:b.count||0} 题</span></div>
        <div class="bank-domains">${(b.domains||[]).map(d=>`<span class="domain-tag">${escapeHtml(d)}</span>`).join('')||'<span style="font-size:12px;color:var(--fg-muted)">未分类</span>'}</div>
        <div class="bank-actions">
          <button class="primary" onclick="viewBankQuestions(${i})">📖 查看题目</button>
          <button class="danger" onclick="deleteBank(${i},'${escapeHtml(b.name)}')">🗑 删除</button>
        </div>
      </div>`).join('')
    }else{badge.textContent='0';list.innerHTML='<div class="banks-empty"><div class="icon">📂</div><p>暂无题库，上传文档开始练习</p></div>'}
  }catch(e){}
}

function viewBankQuestions(idx){
  fetch('/api/banks').then(r=>r.json()).then(d=>{
    const bank=d.banks&&d.banks[idx];
    if(!bank)return;
    const qs=bank._questions||[];
    $('qmodalTitle').textContent=bank.name+' - 共 '+qs.length+' 题';
    if(!qs.length){
      $('qmodalBody').innerHTML='<p style="color:var(--fg-muted);text-align:center;padding:40px 0">暂无题目数据</p>';
    }else{
      $('qmodalBody').innerHTML=qs.map((q,j)=>`<div class="qitem">
        <div class="qitem-q"><strong>#${j+1}</strong> ${escapeHtml(q.question||q.content||'')}</div>
        <div class="qitem-a">${q.answer||q.expected_answer?'📌 '+escapeHtml(q.answer||q.expected_answer||''):''}</div>
        <div style="display:flex;align-items:center;gap:6px;margin-top:3px">
          <div class="qitem-kp">${(q.key_points||q.knowledge_points||[]).map(k=>`<span>${escapeHtml(k)}</span>`).join('')}</div>
          <div class="qitem-diff">${q.difficulty?'难度'+q.difficulty:''}</div>
        </div>
      </div>`).join('')
    }
    $('qmodal').classList.add('active')
  }).catch(()=>{})
}

async function deleteBank(idx,name){
  if(!confirm('确定要删除「'+name+'」吗？此操作不可恢复。'))return;
  try{
    const r=await fetch('/api/banks/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({index:idx})});
    const d=await r.json();
    if(d.ok){showToast('✅ 已删除');fetchBanks();refreshPracticeControls()}
    else showToast('❌ 删除失败')
  }catch(e){showToast('❌ 网络错误')}
}

$('qmodalClose').onclick=()=>$('qmodal').classList.remove('active');
$('qmodal').onclick=e=>{if(e.target===$('qmodal'))$('qmodal').classList.remove('active')}

async function refreshPracticeControls(preserveSelections=true){
  try{
    const saved=preserveSelections?{banks:getActiveChips('pvBankChips')}:{banks:[]};
    const r=await fetch('/api/banks');const d=await r.json();
    practiceBanks=d.banks||[];
    const bankChips=$('pvBankChips');
    bankChips.innerHTML='<button class="chip active" data-value="">全部题库</button>'+
      practiceBanks.map((b,i)=>`<button class="chip ${saved.banks.includes(b.name||'')?'active':''}" data-value="${(b.name||'').replace(/"/g,'&quot;')}">${escapeHtml(b.name||'题库 '+(i+1))}</button>`).join('');
    const hasActiveSpecific=bankChips.querySelectorAll('.chip:not([data-value=""]).active').length>0;
    if(hasActiveSpecific)bankChips.querySelector('.chip[data-value=""]').classList.remove('active');
    bankChips.querySelectorAll('.chip').forEach(c=>c.onclick=chipClickHandler)
  }catch(e){}
}

async function fetchStats(){
  try{
    const r=await fetch('/api/stats');const d=await r.json();
    $('totalQ').textContent=d.total_questions||0;
    $('accuracy').textContent=(d.accuracy!=null?Math.round(d.accuracy*100):0)+'%';
    $('statBankCount').textContent=d.bank_count||0;
    $('streakDays').textContent=d.streak_days||0;
    const bars=$('bankBars');
    if(d.banks&&d.banks.length){
      bars.innerHTML=d.banks.map(b=>`<div class="domain-bar"><div class="bar-label"><span>${escapeHtml(b.name)}</span><span>${b.count}/${b.total} 题</span></div><div class="bar-track"><div class="bar-fill" style="width:${b.total?(b.count/b.total*100).toFixed(0):0}%;${b.count<b.total?'':'background:var(--success)'}"></div></div></div>`).join('')
    }else{bars.innerHTML='<p style="color:var(--fg-muted);font-size:13px">暂无数据</p>'}
    const act=$('activityList');
    if(d.activities&&d.activities.length){
      act.innerHTML=d.activities.map(a=>`<li class="activity-item"><span class="act-icon">${a.icon||'📝'}</span><span class="act-text">${escapeHtml(a.text)}</span><span class="act-time">${escapeHtml(a.time||'')}</span></li>`).join('')
    }else{act.innerHTML='<li style="color:var(--fg-muted);font-size:13px;padding:8px 0">暂无活动记录</li>'}
  }catch(e){}
}

/* Upload helpers */
const uploadLoading=$('uploadLoading'),uploadStatus=$('uploadStatus'),uploadSub=$('uploadSub');
function showUpload(msg,sub){
  uploadLoading.classList.add('active');
  uploadStatus.textContent=msg||'正在上传...';
  uploadSub.textContent=sub||'';
}
function hideUpload(){uploadLoading.classList.remove('active')}
/* Upload bank button */
const bankFileInput=$('bankFileInput');
$('uploadBankBtn').onclick=()=>bankFileInput.click();
bankFileInput.addEventListener('change',async function(){
  const files=this.files;
  if(!files.length)return;
  showUpload(`正在上传 ${files.length} 个文件...`,'读取文件中');
  try{
    for(let i=0;i<files.length;i++){
      const f=files[i];
      showUpload(`正在解析 ${f.name} (${i+1}/${files.length})`,'读取文件内容…');
      const text=await f.text();
      showUpload(`正在分析 ${f.name} (${i+1}/${files.length})`,'AI 提取题目中，请稍候…');
      await fetch('/api/banks/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:f.name,content:text})});
      showUpload(`${i+1}/${files.length} 完成`,'');
    }
    const msg=files.length>1?`✅ 已上传 ${files.length} 个文件`:'✅ 已上传 1 个文件';
    showToast(msg);
    fetchBanks();
    refreshPracticeControls()
  }catch(e){showToast('❌ 上传失败: '+(e.message||''))}
  finally{hideUpload();this.value=''}
});

connect();
fetchBanks();
refreshPracticeControls(false);
restorePracticeSelections();
$('pvDiffChips').querySelectorAll('.chip').forEach(c=>c.onclick=chipClickHandler);
$('pvDomain').textContent='点击右侧「生成题目」开始练习';
refreshPlanIndicator();
loadReviewCards();
</script>
</body>
</html>"""


class WebUIChannel:
    name = "web"
    display_name = "Web UI"

    def __init__(
        self, bus: MessageBus, host: str = "127.0.0.1", port: int = 8769,
        ws_host: str = "127.0.0.1", ws_port: int = 8765,
        provider: Any = None, config_path: str | None = None,
    ) -> None:
        self.bus = bus
        self.host = host
        self.port = port
        self.ws_host = ws_host
        self.ws_port = ws_port
        self._provider = provider
        self._config_path = Path(config_path) if config_path else None
        self._data_dir = (self._config_path.parent / "practice_data") if self._config_path else Path.home() / ".studybot" / "practice_data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._banks_file = self._data_dir / "banks.json"
        self._banks: list[dict] = self._load_banks()
        self._stats: dict = {}
        self._practice = PracticeManager(provider, self._banks) if provider else None
        self._review = ReviewManager(self._data_dir)
        self._memory = MemoryManager(self._data_dir, provider)
        self._plans_file = self._data_dir / "plans.json"
        self._plans: list[dict] = self._load_plans()
        self._server: HTTPServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _load_banks(self) -> list[dict]:
        if self._banks_file.exists():
            try:
                return json.loads(self._banks_file.read_text("utf-8-sig"))
            except Exception:
                return []
        return []

    def _save_banks(self) -> None:
        try:
            self._banks_file.write_text(
                json.dumps(self._banks, ensure_ascii=False, indent=2), "utf-8"
            )
        except Exception:
            pass

    def _load_plans(self) -> list[dict]:
        if self._plans_file.exists():
            try:
                return json.loads(self._plans_file.read_text("utf-8-sig"))
            except Exception:
                return []
        return []

    def _save_plans(self) -> None:
        try:
            self._plans_file.write_text(
                json.dumps(self._plans, ensure_ascii=False, indent=2), "utf-8"
            )
        except Exception:
            pass

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._server = HTTPServer((self.host, self.port), self._make_handler())
        self._server._channel = self
        print(f"✓ Web UI channel: http://{self.host}:{self.port}")
        await self._loop.run_in_executor(None, self._server.serve_forever)

    def _make_handler(self):
        page = PAGE.replace("HOST", self.ws_host).replace("PORT", str(self.ws_port))

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    body = page.encode("utf-8")
                    self._ok("text/html", body)
                elif self.path == "/api/banks":
                    ch = self.server._channel
                    body = json.dumps({"banks": ch._banks}).encode("utf-8")
                    self._ok("application/json", body)
                elif self.path == "/api/stats":
                    ch = self.server._channel
                    pm = ch._practice
                    history = pm.history if pm else []

                    practiced_per_bank: dict[str, int] = {}
                    for h in history:
                        bn = h.get("bank_name", "")
                        if bn:
                            practiced_per_bank[bn] = practiced_per_bank.get(bn, 0) + 1

                    bank_list = []
                    for b in ch._banks:
                        name = b.get("name", "未命名")
                        total = len(b.get("_questions") or [])
                        practiced = practiced_per_bank.get(name, 0)
                        bank_list.append({"name": name, "count": practiced, "total": total})

                    correct = sum(1 for h in history if h.get("evaluation", {}).get("correct"))
                    total = len(history)
                    accuracy = correct / total if total > 0 else 0

                    today = date.today()
                    dates = sorted(set(
                        datetime.fromisoformat(h["timestamp"]).date()
                        for h in history if "timestamp" in h
                    ), reverse=True)
                    streak = 0
                    for i, d in enumerate(dates):
                        expected = today if i == 0 else dates[i-1] - timedelta(days=1)
                        if d == expected:
                            streak += 1
                        else:
                            break

                    activities = []
                    for h in reversed(history[-20:]):
                        ev = h.get("evaluation", {})
                        icon = "✅" if ev.get("correct") else "❌"
                        q_text = (h.get("question") or "")[:60]
                        activities.append({
                            "icon": icon,
                            "text": q_text,
                            "time": f"{ev.get('score', 0)}分",
                        })

                    body = json.dumps({
                        "total_questions": len(history),
                        "accuracy": accuracy,
                        "bank_count": len(bank_list),
                        "streak_days": streak,
                        "banks": bank_list,
                        "activities": activities,
                    }).encode("utf-8")
                    self._ok("application/json", body)
                elif self.path == "/api/settings":
                    prov = self.server._channel._provider
                    body = json.dumps({
                        "api_key": prov.api_key if prov else "",
                        "api_base": prov.api_base if prov else "",
                        "model": prov.default_model if prov else "",
                    }).encode("utf-8")
                    self._ok("application/json", body)
                elif self.path == "/api/practice/question":
                    ch = self.server._channel
                    self._ok("application/json", json.dumps(ch._practice.current or {}).encode("utf-8"))
                elif self.path == "/api/review/due":
                    ch = self.server._channel
                    cards = ch._review.get_due()
                    data = json.dumps({
                        "cards": [
                            {"id": c.id, "question": c.question,
                             "answer": c.answer, "key_points": c.key_points,
                             "domain": c.domain}
                            for c in cards
                        ],
                        "stats": ch._review.stats(),
                    }).encode("utf-8")
                    self._ok("application/json", data)
                elif self.path == "/api/plans":
                    ch = self.server._channel
                    self._ok("application/json", json.dumps({"plans": ch._plans}).encode("utf-8"))
                elif self.path == "/favicon.ico":
                    self._err(204)
                else:
                    self._err(404)

            def do_POST(self):
                if self.path == "/api/banks/upload":
                    self._handle_upload()
                elif self.path == "/api/banks/delete":
                    self._handle_bank_delete()
                elif self.path == "/api/settings":
                    self._handle_save_settings()
                elif self.path == "/api/practice/question":
                    self._handle_practice_question()
                elif self.path == "/api/practice/submit":
                    self._handle_practice_submit()
                elif self.path == "/api/review/rate":
                    self._handle_review_rate()
                elif self.path == "/api/review/add":
                    self._handle_review_add()
                elif self.path == "/api/plans/create":
                    self._handle_plan_create()
                elif self.path == "/api/plans/delete":
                    self._handle_plan_delete()
                elif self.path == "/api/plans/progress":
                    self._handle_plan_progress()
                else:
                    self._err(404)

            def _handle_upload(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                ctype = self.headers.get("Content-Type", "")
                ch = self.server._channel

                # JSON upload: {name, content}
                if ctype.startswith("application/json"):
                    try:
                        data = json.loads(body.decode("utf-8"))
                        fname = data.get("name", "unnamed")
                        fcontent = data.get("content", "")
                        entry = {"name": fname, "count": 0, "domains": [], "content": fcontent}
                        ch._banks.append(entry)
                        # Schedule content analysis
                        pm = ch._practice
                        if pm and fcontent:
                            try:
                                future = asyncio.run_coroutine_threadsafe(
                                    pm.analyze_content(fname, fcontent), ch._loop
                                )
                                info = future.result(timeout=120)
                                entry.update(info)
                            except Exception:
                                pass
                        ch._save_banks()
                    except Exception:
                        pass
                    self._ok("application/json", json.dumps({"ok": True}).encode("utf-8"))
                    return

                # Multipart upload (legacy)
                if "boundary=" in ctype:
                    boundary = ctype.split("boundary=")[1].split(";")[0].strip('"')
                    parts = body.split(b"--" + boundary.encode())
                    import urllib.parse
                    for part in parts:
                        if not part or part.strip() in (b"--", b"", b"\r\n"):
                            continue
                        hdr_end = part.find(b"\r\n\r\n")
                        if hdr_end == -1:
                            continue
                        headers_raw = part[:hdr_end].decode("utf-8", errors="replace")
                        data = part[hdr_end + 4:].rstrip(b"\r\n--")
                        fname = None
                        for line in headers_raw.split("\r\n"):
                            if line.lower().startswith("content-disposition"):
                                if 'filename="' in line:
                                    fname = line.split('filename="')[1].split('"')[0]
                                elif "filename*=utf-8''" in line:
                                    fname = urllib.parse.unquote(line.split("utf-8''")[1].split(";")[0])
                        if fname and data:
                            fname = urllib.parse.unquote(fname)
                            self.server._channel._banks.append({"name": fname, "count": 0, "domains": []})
                self._ok("application/json", json.dumps({"ok": True}).encode("utf-8"))

            def _handle_bank_delete(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                ch = self.server._channel
                try:
                    data = json.loads(body.decode("utf-8"))
                    idx = int(data.get("index", -1))
                    if 0 <= idx < len(ch._banks):
                        removed = ch._banks.pop(idx)
                        ch._save_banks()
                        self._ok("application/json", json.dumps({"ok": True}).encode("utf-8"))
                    else:
                        self._ok("application/json", json.dumps({"ok": False, "error": "invalid index"}).encode("utf-8"))
                except Exception:
                    self._ok("application/json", json.dumps({"ok": False, "error": "invalid request"}).encode("utf-8"))

            def _handle_save_settings(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                try:
                    data = json.loads(body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self._err(400)
                    return

                ch = self.server._channel
                prov = ch._provider
                apply_restart = []

                # Provider settings — apply immediately
                if prov and any(k in data for k in ("api_key", "api_base", "model")):
                    prov.update_config(
                        api_key=data.get("api_key"),
                        api_base=data.get("api_base"),
                        model=data.get("model"),
                    )

                # Feishu settings — save to file only (needs restart)
                if "feishu_app_id" in data or "feishu_app_secret" in data:
                    apply_restart.append("飞书")

                # Persist to config.json
                cfg_path = ch._config_path
                if cfg_path:
                    try:
                        cfg = {}
                        if cfg_path.exists():
                            with open(cfg_path, "r", encoding="utf-8-sig") as f:
                                cfg = json.load(f)
                        prov_cfg = cfg.setdefault("provider", {})
                        if "api_key" in data:
                            prov_cfg["api_key"] = data["api_key"]
                        if "api_base" in data:
                            prov_cfg["api_base"] = data["api_base"]
                        if "model" in data:
                            prov_cfg["model"] = data["model"]
                        if "feishu_app_id" in data:
                            cfg.setdefault("feishu", {})["app_id"] = data["feishu_app_id"]
                        if "feishu_app_secret" in data:
                            cfg.setdefault("feishu", {})["app_secret"] = data["feishu_app_secret"]
                        cfg_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(cfg_path, "w", encoding="utf-8") as f:
                            json.dump(cfg, f, ensure_ascii=False, indent=2)
                    except Exception as e:
                        self._ok("application/json", json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
                        return

                resp = {"ok": True}
                if apply_restart:
                    resp["restart_required"] = apply_restart
                self._ok("application/json", json.dumps(resp).encode("utf-8"))

            def _read_body(self) -> dict:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                try:
                    return json.loads(body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return {}

            def _handle_practice_question(self):
                data = self._read_body()
                bank_names: list[str] = data.get("bank_names", [])
                difficulties: list[str] = data.get("difficulties", [])
                ch = self.server._channel
                pm = ch._practice
                if not pm:
                    self._ok("application/json", json.dumps({"error": "No provider"}).encode("utf-8"))
                    return
                try:
                    mem_ctx = ch._memory.get_context() if hasattr(ch, '_memory') and ch._memory else ""
                    future = asyncio.run_coroutine_threadsafe(
                        pm.generate_question(bank_names, difficulties, memory_context=mem_ctx), ch._loop
                    )
                    result = future.result(timeout=30)
                    self._ok("application/json", json.dumps(result).encode("utf-8"))
                except Exception as e:
                    self._ok("application/json", json.dumps({"error": str(e)}).encode("utf-8"))

            def _handle_practice_submit(self):
                data = self._read_body()
                ch = self.server._channel
                pm = ch._practice
                if not pm or not pm.current:
                    self._ok("application/json", json.dumps({"error": "No active question"}).encode("utf-8"))
                    return
                user_answer = data.get("answer", "")
                try:
                    mem_ctx = ch._memory.get_context(domain=pm.current.get("bank_name", "")) if hasattr(ch, '_memory') and ch._memory else ""
                    future = asyncio.run_coroutine_threadsafe(
                        pm.evaluate_answer(
                            pm.current.get("question", ""),
                            pm.current.get("expected_answer", ""),
                            user_answer,
                            memory_context=mem_ctx,
                        ),
                        ch._loop,
                    )
                    result = future.result(timeout=30)
                    pm.history.append({
                        "question": pm.current.get("question", ""),
                        "answer": user_answer,
                        "evaluation": result,
                        "timestamp": datetime.now().isoformat(),
                        "bank_name": pm.current.get("bank_name", ""),
                    })
                    # Fire-and-forget reflection
                    if hasattr(ch, '_memory') and ch._memory:
                        asyncio.run_coroutine_threadsafe(
                            ch._memory.reflect(
                                question=pm.current.get("question", ""),
                                expected=pm.current.get("expected_answer", ""),
                                answer=user_answer,
                                score=result.get("score", 0),
                                feedback=result.get("feedback", ""),
                                missing=result.get("missing_points", []),
                                domain=pm.current.get("bank_name", ""),
                            ),
                            ch._loop,
                        )
                    self._ok("application/json", json.dumps(result).encode("utf-8"))
                except Exception as e:
                    self._ok("application/json", json.dumps({"error": str(e)}).encode("utf-8"))

            def _handle_review_rate(self):
                data = self._read_body()
                ch = self.server._channel
                card = ch._review.rate(data.get("id", ""), int(data.get("quality", 3)))
                if card:
                    self._ok("application/json", json.dumps({"ok": True}).encode("utf-8"))
                else:
                    self._ok("application/json", json.dumps({"error": "Card not found"}).encode("utf-8"))

            def _handle_review_add(self):
                data = self._read_body()
                ch = self.server._channel
                card = ch._review.add_card(
                    question=data.get("question", ""),
                    answer=data.get("answer", ""),
                    key_points=data.get("key_points", ""),
                    domain=data.get("domain", ""),
                )
                stats = ch._review.stats()
                self._ok("application/json", json.dumps({"ok": True, "id": card.id, "stats": stats}).encode("utf-8"))

            def _handle_plan_create(self):
                data = self._read_body()
                ch = self.server._channel
                bank_names = data.get("bank_names", [])
                qpd = int(data.get("questions_per_day", 10))
                total_days = int(data.get("total_days", 30))
                # Collect and shuffle all questions from selected banks
                all_qs: list[dict] = []
                for b in ch._banks:
                    name = b.get("name", "")
                    if bank_names and name not in bank_names:
                        continue
                    for q in (b.get("_questions") or b.get("questions", [])):
                        all_qs.append({
                            "question": q.get("question", q.get("content", "")),
                            "expected_answer": q.get("answer", q.get("expected_answer", "")),
                            "key_points": q.get("key_points", q.get("knowledge_points", [])),
                            "bank_name": name,
                        })
                random.shuffle(all_qs)
                # Assign questions to days (flat array, frontend slices by day)
                total_needed = qpd * total_days
                assigned = all_qs[:total_needed]
                plan = {
                    "id": uuid.uuid4().hex[:12],
                    "name": data.get("name", "未命名计划"),
                    "bank_names": bank_names,
                    "questions_per_day": qpd,
                    "total_days": total_days,
                    "created": date.today().isoformat(),
                    "logs": {},
                    "questions": assigned,
                }
                ch._plans.append(plan)
                ch._save_plans()
                self._ok("application/json", json.dumps({"ok": True, "plan": plan}).encode("utf-8"))

            def _handle_plan_delete(self):
                data = self._read_body()
                ch = self.server._channel
                ch._plans = [p for p in ch._plans if p.get("id") != data.get("id")]
                ch._save_plans()
                self._ok("application/json", json.dumps({"ok": True}).encode("utf-8"))

            def _handle_plan_progress(self):
                data = self._read_body()
                ch = self.server._channel
                for p in ch._plans:
                    if p.get("id") == data.get("id"):
                        p["logs"] = data.get("logs", {})
                        break
                ch._save_plans()
                self._ok("application/json", json.dumps({"ok": True}).encode("utf-8"))

            def _ok(self, content_type, body):
                self.send_response(200)
                self.send_header("Content-Type", content_type + "; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)

            def _err(self, code):
                self.send_response(code)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler

    async def stop(self) -> None:
        if self._server:
            self._server.shutdown()
