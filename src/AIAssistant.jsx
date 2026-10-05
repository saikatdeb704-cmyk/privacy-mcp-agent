import { useState } from 'react';
import './AIAssistant.css';

const AI_TOOLS = [
  { id: 'cover-letter', name: '📝 Cover Letter', description: 'Generate a personalized cover letter based on your application.' },
  { id: 'interview-prep', name: '🎤 Interview Prep', description: 'Get role-specific questions and expert tips.' },
  { id: 'resume-tailor', name: '🎯 Resume Tailor', description: 'Extract keywords and suggest bullet points.' },
  { id: 'insights', name: '🧠 Insights', description: 'Analyze next steps and strategy.' }
];

export function AIAssistant({ applications, onClose }) {
  const [selectedAppId, setSelectedAppId] = useState('');
  const [selectedTool, setSelectedTool] = useState(AI_TOOLS[0].id);
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState('');

  const selectedApp = applications.find(a => a.id === selectedAppId);

  const handleGenerate = () => {
    if (!selectedApp) return;
    setIsGenerating(true);
    setResult('');
    
    setTimeout(() => {
      setIsGenerating(false);
      setResult(getMockResponse(selectedTool, selectedApp));
    }, 2000);
  };

  return (
    <div className="ai-modal-overlay" onClick={onClose}>
      <div className="ai-modal" onClick={e => e.stopPropagation()}>
        <div className="ai-modal-header">
          <h2 className="ai-modal-title">✨ AI Assistant</h2>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>
        
        <div className="ai-modal-body">
          <div className="ai-sidebar">
            <div className="ai-form-group">
              <label>Select Application</label>
              <select 
                value={selectedAppId} 
                onChange={e => setSelectedAppId(e.target.value)}
                className="ai-select"
              >
                <option value="">-- Choose an application --</option>
                {applications.map(app => (
                  <option key={app.id} value={app.id}>
                    {app.company} - {app.role || 'General'}
                  </option>
                ))}
              </select>
            </div>
            
            <div className="ai-tools-list">
              <label>Select Tool</label>
              {AI_TOOLS.map(tool => (
                <div 
                  key={tool.id} 
                  className={`ai-tool-card ${selectedTool === tool.id ? 'active' : ''}`}
                  onClick={() => setSelectedTool(tool.id)}
                >
                  <div className="ai-tool-name">{tool.name}</div>
                  <div className="ai-tool-desc">{tool.description}</div>
                </div>
              ))}
            </div>
            
            <button 
              className="btn btn-primary ai-generate-btn" 
              onClick={handleGenerate}
              disabled={!selectedAppId || isGenerating}
            >
              {isGenerating ? '✨ Generating...' : '✨ Generate'}
            </button>
          </div>
          
          <div className="ai-content-area">
            {isGenerating ? (
              <div className="ai-loading-state">
                <div className="ai-spinner"></div>
                <p>AI is analyzing {selectedApp?.company || 'data'}...</p>
              </div>
            ) : result ? (
              <div className="ai-result-content">
                <div dangerouslySetInnerHTML={{ __html: result }} />
              </div>
            ) : (
              <div className="ai-empty-state">
                <div className="ai-empty-icon">🤖</div>
                <h3>Ready to assist!</h3>
                <p>Select an application and a tool to get started.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function getMockResponse(toolId, app) {
  const company = app.company || 'the company';
  const role = app.role || 'this role';
  
  if (toolId === 'cover-letter') {
    return `
      <div class="ai-doc">
        <h3>Cover Letter Draft</h3>
        <p>Dear Hiring Manager at <strong>${company}</strong>,</p>
        <p>I am writing to express my strong interest in the <strong>${role}</strong> position. With a solid foundation in software development and a passion for building scalable solutions, I am excited about the opportunity to contribute to ${company}'s innovative projects.</p>
        <p>In my recent academic and personal projects, I have developed expertise in modern web technologies and backend architecture. I admire ${company}'s commitment to excellence and believe my skills align perfectly with your team's goals.</p>
        <p>Thank you for considering my application. I look forward to the possibility of discussing how I can add value to ${company}.</p>
        <p>Sincerely,<br/>[Your Name]</p>
      </div>
    `;
  }
  if (toolId === 'interview-prep') {
    return `
      <div class="ai-doc">
        <h3>Interview Prep for ${company}</h3>
        <ul>
          <li><strong>Behavioral:</strong> Why ${company}? What aligns you with our mission?</li>
          <li><strong>Technical:</strong> Expect questions on data structures, algorithms, and system design relevant to ${role}.</li>
          <li><strong>Company Research:</strong> Review ${company}'s recent product launches and engineering blog.</li>
          <li><strong>Questions to Ask:</strong> "What does success look like for a ${role} in the first 90 days?"</li>
        </ul>
      </div>
    `;
  }
  if (toolId === 'resume-tailor') {
    return `
      <div class="ai-doc">
        <h3>Resume Optimization for ${role}</h3>
        <h4>Key Skills to Highlight:</h4>
        <div class="ai-tags">
          <span class="ai-tag">Scalability</span>
          <span class="ai-tag">API Design</span>
          <span class="ai-tag">Team Collaboration</span>
          <span class="ai-tag">Agile Methodology</span>
        </div>
        <h4>Suggested Bullet Points:</h4>
        <ul>
          <li>Developed and optimized backend services resulting in a 20% performance increase, highly relevant for ${company}.</li>
          <li>Collaborated with cross-functional teams to deliver features on time, aligning with ${role} requirements.</li>
        </ul>
      </div>
    `;
  }
  if (toolId === 'insights') {
    return `
      <div class="ai-doc">
        <h3>Application Insights</h3>
        <p><strong>Status Analysis:</strong> You applied recently. The current status is <em>${app.status}</em>.</p>
        <p><strong>Next Best Action:</strong> Consider reaching out to a recruiter on LinkedIn to follow up on your ${company} application.</p>
        <p><strong>Competitiveness:</strong> ${company} is highly competitive for ${role} roles. Ensure your portfolio highlights end-to-end projects.</p>
      </div>
    `;
  }
  return '<p>No result</p>';
}
