:root {
  --bg: #0d1321;
  --panel: #171f32;
  --panel-alt: #202d4d;
  --accent: #f4c95d;
  --accent-2: #b8d8ff;
  --text: #edf2ff;
  --muted: #b9c4d7;
  --success: #7ae582;
  --shadow: rgba(0, 0, 0, 0.2);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: Arial, Helvetica, sans-serif;
  background: linear-gradient(180deg, #0d1321 0%, #16233d 100%);
  color: var(--text);
}

.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px 20px 60px;
}

.hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  margin-bottom: 28px;
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-size: 12px;
}

h1 {
  margin: 0;
  font-size: clamp(2rem, 5vw, 3.4rem);
}

.hero-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.hero-badges span {
  background: rgba(244, 201, 93, 0.12);
  border: 1px solid rgba(244, 201, 93, 0.5);
  color: var(--accent);
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
}

.layout {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 24px;
}

.panel {
  background: rgba(23, 31, 50, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  box-shadow: 0 18px 40px var(--shadow);
  padding: 22px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 18px;
}

.panel-header h2 {
  margin: 0;
  font-size: 1.2rem;
}

select, input, button {
  border-radius: 10px;
  border: none;
  font-size: 15px;
}

select, input {
  padding: 10px 12px;
  background: var(--panel-alt);
  color: var(--text);
}

button {
  padding: 10px 16px;
  background: linear-gradient(135deg, var(--accent), #e9a728);
  color: #1b1b1b;
  font-weight: 700;
  cursor: pointer;
}

.summary-box {
  background: linear-gradient(180deg, rgba(184, 216, 255, 0.09), rgba(255, 255, 255, 0.02));
  border: 1px solid rgba(184, 216, 255, 0.15);
  border-radius: 12px;
  padding: 16px;
  line-height: 1.6;
  color: var(--muted);
  margin-bottom: 16px;
}

.agent-list {
  display: grid;
  gap: 12px;
}

.agent-card {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 14px;
}

.agent-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.agent-name {
  font-weight: 700;
}

.agent-score {
  color: var(--success);
  font-weight: 700;
}

.agent-specialty {
  color: var(--muted);
  font-size: 0.85rem;
  margin-bottom: 8px;
}

.chat-panel {
  display: flex;
  flex-direction: column;
}

.chat-messages {
  min-height: 320px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 14px;
}

.message {
  max-width: 85%;
  padding: 12px 14px;
  border-radius: 12px;
  line-height: 1.5;
}

.message.bot {
  background: #243865;
}

.message.user {
  background: #2b5d4d;
  align-self: flex-end;
}

.chat-form {
  display: flex;
  gap: 12px;
}

.chat-form input {
  flex: 1;
}

@media (max-width: 860px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .hero {
    flex-direction: column;
    align-items: flex-start;
  }
}
