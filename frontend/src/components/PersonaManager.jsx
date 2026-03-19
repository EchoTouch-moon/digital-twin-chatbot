import React, { useState } from 'react';

/**
 * 角色管理抽屉内容 - 液态玻璃风格
 */
const PersonaManager = ({
  personas,
  selectedPersona,
  memories,
  userProfile,
  memorySummaries,
  isLoading,
  error,
  onSelectPersona,
  onCreatePersona,
  onGenerateProfile,
}) => {
  const [isCreating, setIsCreating] = useState(false);
  const [newPersonaName, setNewPersonaName] = useState('');
  const [newPersonaDescription, setNewPersonaDescription] = useState('');
  const [activeTab, setActiveTab] = useState('personas');

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newPersonaName.trim()) return;
    try {
      await onCreatePersona(newPersonaName.trim(), newPersonaDescription.trim());
      setNewPersonaName('');
      setNewPersonaDescription('');
      setIsCreating(false);
    } catch (err) {}
  };

  const handleGenerateProfile = async () => {
    if (selectedPersona?.id) {
      await onGenerateProfile(selectedPersona.id);
    }
  };

  const getStageName = (stage) => {
    const stageNames = {
      'acquaintance': '初识阶段',
      'friend': '朋友阶段',
      'close_friend': '好友阶段',
      'best_friend': '挚友阶段'
    };
    return stageNames[stage] || stage;
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* 当前角色头部 */}
      {selectedPersona && (
        <div className="flex-shrink-0 p-5 border-b border-gray-200/30">
          <div className="flex gap-4">
            <div
              className="rounded-full flex items-center justify-center text-white text-xl font-medium flex-shrink-0"
              style={{
                width: '56px',
                height: '56px',
                background: 'linear-gradient(135deg, #FF6B6B, #FFA07A)',
                boxShadow: '0 4px 15px rgba(255,107,107,0.25)'
              }}
            >
              {selectedPersona.name.charAt(0)}
            </div>
            <div className="flex-1" style={{ minWidth: 0 }}>
              <h2 className="text-lg font-semibold text-gray-800">{selectedPersona.name}</h2>
              {selectedPersona.description && (
                <p className="text-sm text-gray-500 mt-1" style={{ whiteSpace: 'pre-wrap' }}>
                  {selectedPersona.description}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 分段控件 */}
      <div className="p-4">
        <div
          className="rounded-xl p-1 flex"
          style={{ background: 'rgba(0,0,0,0.05)' }}
        >
          {['personas', 'memories', 'profile'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 py-2.5 text-sm rounded-lg transition-all duration-200 ${
                activeTab === tab
                  ? 'bg-white text-gray-800 font-medium shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab === 'personas' && '角色'}
              {tab === 'memories' && '记忆'}
              {tab === 'profile' && '画像'}
            </button>
          ))}
        </div>
      </div>

      {/* 内容区域 */}
      <div className="flex-1 overflow-y-auto chat-scrollbar">
        {/* 角色列表 */}
        {activeTab === 'personas' && (
          <div className="p-4 space-y-2">
            {/* 创建角色按钮 */}
            {!isCreating ? (
              <button
                onClick={() => setIsCreating(true)}
                className="w-full py-3.5 text-sm text-gray-500 bg-white/40 rounded-xl hover:bg-white/60 transition-colors border border-gray-200/50"
              >
                + 创建新角色
              </button>
            ) : (
              <form onSubmit={handleCreate} className="p-4 bg-white/50 rounded-xl space-y-3 border border-gray-200/30">
                <input
                  type="text"
                  placeholder="角色名称"
                  value={newPersonaName}
                  onChange={(e) => setNewPersonaName(e.target.value)}
                  className="w-full px-4 py-3 bg-white/70 rounded-xl text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:bg-white"
                  autoFocus
                />
                <textarea
                  placeholder="角色描述（可选）"
                  value={newPersonaDescription}
                  onChange={(e) => setNewPersonaDescription(e.target.value)}
                  rows={2}
                  className="w-full px-4 py-3 bg-white/70 rounded-xl text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:bg-white resize-none"
                />
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={!newPersonaName.trim() || isLoading}
                    className="flex-1 py-2.5 bg-gray-800 text-white text-sm rounded-full font-medium disabled:bg-gray-300 disabled:text-gray-500"
                  >
                    创建
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsCreating(false);
                      setNewPersonaName('');
                      setNewPersonaDescription('');
                    }}
                    className="flex-1 py-2.5 bg-gray-100 text-gray-600 text-sm rounded-full font-medium"
                  >
                    取消
                  </button>
                </div>
              </form>
            )}

            {/* 错误提示 */}
            {error && (
              <div className="p-3 bg-red-50 text-red-500 text-sm rounded-xl">
                {error}
              </div>
            )}

            {/* 角色列表 */}
            {personas.map((persona) => (
              <button
                key={persona.id}
                onClick={() => onSelectPersona(persona)}
                className={`w-full p-3 rounded-xl flex items-center gap-3 transition-all ${
                  selectedPersona?.id === persona.id
                    ? 'bg-white/70 shadow-sm'
                    : 'bg-white/30 hover:bg-white/50'
                }`}
              >
                <div
                  className="w-11 h-11 rounded-full flex items-center justify-center text-white text-base flex-shrink-0"
                  style={{
                    background: 'linear-gradient(135deg, #FF6B6B, #FFA07A)',
                  }}
                >
                  {persona.name.charAt(0)}
                </div>
                <div className="flex-1 text-left min-w-0">
                  <div className="text-sm font-medium text-gray-800">{persona.name}</div>
                  {persona.description && (
                    <div className="text-xs text-gray-500 mt-0.5" style={{ whiteSpace: 'normal' }}>
                      {persona.description}
                    </div>
                  )}
                </div>
              </button>
            ))}
          </div>
        )}

        {/* 记忆列表 */}
        {activeTab === 'memories' && (
          <div className="p-4 space-y-3">
            {memories.length === 0 ? (
              <div className="text-center py-10 text-gray-400 text-sm">
                还没有记忆，与角色对话会自动提取
              </div>
            ) : (
              memories.map((memory) => (
                <div
                  key={memory.id}
                  className="p-4 bg-white/40 rounded-xl border border-gray-200/30"
                >
                  <div className="flex items-start gap-3">
                    <span className="text-lg">
                      {memory.memory_type === 'preference' && '❤️'}
                      {memory.memory_type === 'fact' && '💡'}
                      {memory.memory_type === 'event' && '📅'}
                      {memory.memory_type === 'topic' && '💬'}
                    </span>
                    <div className="flex-1">
                      <p className="text-sm text-gray-700">{memory.content}</p>
                      <div className="flex items-center gap-2 mt-2 text-xs text-gray-400">
                        <span className="px-2 py-0.5 bg-white/60 rounded">{memory.memory_type}</span>
                        <span>重要性: {memory.importance_score?.toFixed(1)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* 用户画像 */}
        {activeTab === 'profile' && (
          <div className="p-4 space-y-4">
            {!selectedPersona ? (
              <div className="text-center py-10 text-gray-400 text-sm">
                请先选择一个角色
              </div>
            ) : !userProfile || userProfile.conversation_count === 0 ? (
              <div className="text-center py-10">
                <div className="text-gray-500 text-sm mb-5">还没有用户画像</div>
                <button
                  onClick={handleGenerateProfile}
                  disabled={isLoading}
                  className="px-8 py-3 bg-gray-800 text-white text-sm rounded-full font-medium disabled:bg-gray-300 disabled:text-gray-500"
                >
                  {isLoading ? '生成中...' : '生成画像'}
                </button>
              </div>
            ) : (
              <>
                {/* 关系阶段 */}
                <div
                  className="p-5 rounded-xl border"
                  style={{
                    background: 'linear-gradient(135deg, rgba(50,173,230,0.15), rgba(255,45,85,0.1))',
                    borderColor: 'rgba(255,255,255,0.5)'
                  }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-gray-500">关系阶段</span>
                    <span className="text-xs px-3 py-1 bg-white/60 text-gray-600 rounded-full">
                      信任度 {Math.round(userProfile.trust_level * 100)}%
                    </span>
                  </div>
                  <div className="text-lg font-semibold text-gray-800">
                    {getStageName(userProfile.relationship_stage)}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    基于 {userProfile.conversation_count} 条记忆
                  </div>
                </div>

                {/* 兴趣爱好 */}
                {userProfile.interests?.length > 0 && (
                  <div className="p-4 bg-white/40 rounded-xl border border-gray-200/30">
                    <h4 className="text-sm font-medium text-gray-700 mb-3">兴趣爱好</h4>
                    <div className="flex flex-wrap gap-2">
                      {userProfile.interests.map((interest, idx) => (
                        <span
                          key={idx}
                          className="px-3 py-1.5 bg-white/70 rounded-lg text-xs text-gray-600"
                        >
                          {interest}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* 沟通风格 */}
                {userProfile.communication_style && (
                  <div className="p-4 bg-white/40 rounded-xl border border-gray-200/30">
                    <h4 className="text-sm font-medium text-gray-700 mb-2">沟通特点</h4>
                    <p className="text-sm text-gray-600">{userProfile.communication_style}</p>
                  </div>
                )}

                {/* 背景信息 */}
                {userProfile.background_summary && (
                  <div className="p-4 bg-white/40 rounded-xl border border-gray-200/30">
                    <h4 className="text-sm font-medium text-gray-700 mb-2">背景信息</h4>
                    <p className="text-sm text-gray-600 whitespace-pre-line">
                      {userProfile.background_summary}
                    </p>
                  </div>
                )}

                {/* 记忆摘要 */}
                {memorySummaries?.length > 0 && (
                  <div className="p-4 bg-white/40 rounded-xl border border-gray-200/30">
                    <h4 className="text-sm font-medium text-gray-700 mb-3">记忆摘要</h4>
                    <div className="space-y-2">
                      {memorySummaries.map((summary) => (
                        <div key={summary.id} className="p-3 bg-white/60 rounded-lg">
                          <div className="text-xs font-medium text-gray-700">{summary.title}</div>
                          <div className="text-xs text-gray-500 mt-1 line-clamp-2">
                            {summary.content}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 重新生成按钮 */}
                <button
                  onClick={handleGenerateProfile}
                  disabled={isLoading}
                  className="w-full py-3 bg-gray-100 text-gray-500 text-sm rounded-xl hover:bg-gray-200 transition-colors"
                >
                  {isLoading ? '更新中...' : '重新生成画像'}
                </button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default PersonaManager;