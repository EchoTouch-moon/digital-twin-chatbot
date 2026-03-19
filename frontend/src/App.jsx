import React, { useState } from 'react';
import ChatInterface from './components/ChatInterface';
import PersonaManager from './components/PersonaManager';
import Drawer from './components/Drawer';
import { usePersonas } from './hooks/usePersonas';

/**
 * 应用主组件 - Apple 极简风格
 */
function App() {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  const {
    personas,
    selectedPersona,
    memories,
    userProfile,
    memorySummaries,
    isLoading,
    error,
    createPersona,
    selectPersona,
    generateUserProfile,
  } = usePersonas();

  const handleSelectPersona = (persona) => {
    selectPersona(persona);
    setIsDrawerOpen(false);
  };

  return (
    <div className="h-screen overflow-hidden">
      {/* 聊天界面 */}
      <ChatInterface
        selectedPersona={selectedPersona}
        onToggleSidebar={() => setIsDrawerOpen(!isDrawerOpen)}
        isSidebarVisible={isDrawerOpen}
      />

      {/* 抽屉式侧边栏 */}
      <Drawer
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
        width={320}
      >
        <PersonaManager
          personas={personas}
          selectedPersona={selectedPersona}
          memories={memories}
          userProfile={userProfile}
          memorySummaries={memorySummaries}
          isLoading={isLoading}
          error={error}
          onSelectPersona={handleSelectPersona}
          onCreatePersona={createPersona}
          onGenerateProfile={generateUserProfile}
        />
      </Drawer>
    </div>
  );
}

export default App;