import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import 'highlight.js/lib/common'; // Import common languages
import mermaid from 'mermaid';

// Initialize highlight.js theme (reusing existing logic)
let themeLoaded = false;
async function loadHighlightTheme() {
  if (themeLoaded) return;
  try {
    const cssModule = await import('highlight.js/styles/github-dark.css?inline');
    const style = document.createElement('style');
    style.textContent = `
      ${cssModule.default}
      .code-block-container .hljs { background: transparent !important; color: #c9d1d9 !important; }
      /* ... other highlight overrides ... */
    `;
    style.setAttribute('data-hljs-theme', 'github-dark');
    document.head.appendChild(style);
    themeLoaded = true;
  } catch (error) {
    console.warn('Failed to load highlight.js theme', error);
  }
}

// Initialize mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  securityLevel: 'loose',
  fontFamily: 'monospace',
});

// --- Album Logic ---
let albumCounter = 0;

declare global {
  interface Window {
    moveSlide: (albumId: string, direction: number) => void;
    goToSlide: (albumId: string, index: number) => void;
    copyCodeBlock: (button: HTMLElement) => Promise<void>;
  }
}

function setupCarouselFunctions() {
  if (typeof window === 'undefined') return;

  window.moveSlide = (albumId: string, direction: number) => {
    const container = document.getElementById(albumId);
    if (!container) return;

    const slides = container.querySelectorAll('.carousel-slide');
    let activeIndex = 0;
    slides.forEach((slide, idx) => {
      if (slide.classList.contains('active')) activeIndex = idx;
    });

    let newIndex = activeIndex + direction;
    if (newIndex >= slides.length) newIndex = 0;
    if (newIndex < 0) newIndex = slides.length - 1;

    updateCarouselUI(container as HTMLElement, newIndex);
  };

  window.goToSlide = (albumId: string, index: number) => {
    const container = document.getElementById(albumId);
    if (container) updateCarouselUI(container as HTMLElement, index);
  };
}

function updateCarouselUI(container: HTMLElement, newIndex: number) {
  // Update Slides
  const slides = container.querySelectorAll('.carousel-slide');
  slides.forEach((slide, idx) => {
    if (idx === newIndex) slide.classList.add('active');
    else slide.classList.remove('active');
  });

  // Update Thumbs (if exist)
  const thumbs = container.querySelectorAll('.carousel-thumb-item');
  thumbs.forEach((thumb, idx) => {
    if (idx === newIndex) thumb.classList.add('active');
    else thumb.classList.remove('active');
  });
}

// Initialize global functions immediately
setupCarouselFunctions();

const renderAlbum = (str: string, lang: string) => {
  const parts = lang.trim().split(/\s+/).filter(Boolean);
  const mode = parts[1] || 'grid';
  const lines = str.trim().split('\n');
  const items: Array<{ url: string; caption: string; widthVal: string }> = [];

  lines.forEach((line) => {
    const trimmedLine = line.trim();
    if (!trimmedLine) return;

    const regex = /^!\[(.*?)\]\((.*?)\)$/;
    const match = trimmedLine.match(regex);
    if (match) {
      const rawAlt = match[1];
      const url = match[2];
      let caption = rawAlt;
      let widthVal = '';

      if (rawAlt.includes('|')) {
        const altParts = rawAlt.split('|');
        caption = altParts[0].trim();
        widthVal = altParts[1].trim();
      }
      items.push({ url, caption, widthVal });
    }
  });

  if (items.length === 0) return '';

  if (mode === 'grid') {
    let html = '<div class="album-grid">';
    items.forEach((item) => {
      let widthStyle = '';
      if (item.widthVal && item.widthVal !== 'auto') {
        widthStyle = `style="width: ${item.widthVal}; flex: 0 0 auto;"`;
      }
      html += `
            <div class="album-item" ${widthStyle}>
                <img src="${item.url}" alt="${item.caption}" loading="lazy" />
                ${item.caption ? `<div class="album-caption">${item.caption}</div>` : ''}
            </div>`;
    });
    html += '</div>';
    return html;
  }

  // Carousel / Thumbnail
  const albumId = `album-${albumCounter++}`;
  const hasThumbs = mode === 'thumbnail';

  let html = `<div class="album-carousel-container" id="${albumId}" data-mode="${mode}">`;

  html += `<div class="carousel-stage">
`;
  html += `<button class="carousel-nav-btn carousel-prev" onclick="moveSlide('${albumId}', -1)">❮</button>`;
  html += `<button class="carousel-nav-btn carousel-next" onclick="moveSlide('${albumId}', 1)">❯</button>`;

  items.forEach((item, idx) => {
    const activeClass = idx === 0 ? 'active' : '';
    html += `
        <div class="carousel-slide ${activeClass}" data-index="${idx}">
            <img src="${item.url}" alt="${item.caption}">
            ${item.caption ? `<div class="carousel-caption-overlay">${item.caption}</div>` : ''}
        </div>`;
  });
  html += `</div>`;

  if (hasThumbs) {
    html += `<div class="carousel-thumbs">
`;
    items.forEach((item, idx) => {
      const activeClass = idx === 0 ? 'active' : '';
      html += `
            <div class="carousel-thumb-item ${activeClass}" 
                 onclick="goToSlide('${albumId}', ${idx})" 
                 data-index="${idx}">
                <img src="${item.url}">
            </div>`;
    });
    html += `</div>`;
  }

  html += `</div>`;
  return html;
};

// --- Markdown-it Config ---
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  highlight: function (str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value;
      } catch (__) {}
    }
    return '';
  }
});

// Custom Fence Rule
const defaultFence = md.renderer.rules.fence || function (tokens: any, idx: any, options: any, env: any, self: any) {
  return self.renderToken(tokens, idx, options);
};

md.renderer.rules.fence = function (tokens: any, idx: any, options: any, env: any, self: any) {
  const token = tokens[idx];
  const info = token.info ? token.info.trim() : '';
  const parts = info.split(/\s+/).filter(Boolean);
  const langKey = parts[0] || '';
  const content = token.content;

  if (langKey === 'album') {
    return renderAlbum(content, info);
  }
  if (langKey === 'mermaid') {
    return `<div class="mermaid">${content}</div>`;
  }

  return defaultFence(tokens, idx, options, env, self);
};

// Custom Image Rule
md.renderer.rules.image = function (tokens: any, idx: any, options: any, env: any, self: any) {
    const token = tokens[idx];
    const src = token.attrGet('src') || '';
    const rawAlt = token.children
        ? self.renderInlineAsText(token.children, options, env)
        : '';

    let caption = rawAlt;
    let widthVal = '';

    if (rawAlt.includes('|')) {
        const altParts = rawAlt.split('|');
        caption = altParts[0].trim();
        widthVal = altParts[1].trim();
    }

    let imgHtml = `<img src="${src}" alt="${caption}" class="max-w-full h-auto rounded-lg shadow-sm my-2" loading="lazy"`;

    if (widthVal && widthVal !== 'auto') {
        imgHtml += ` style="width: ${widthVal}"`;
    }

    imgHtml += '>';

    if (caption) {
        return `<figure class="image-figure">${imgHtml}<figcaption class="image-caption">${caption}</figcaption></figure>`;
    }

    return imgHtml;
};

// Copy function (same as before)
if (typeof window !== 'undefined') {
  (window as any).copyCodeBlock = async (button: HTMLElement) => {
    try {
      const text = button.getAttribute('data-copy-text') || '';
      const decodedText = text.replace(/&quot;/g, '"').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
      
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(decodedText);
      } else {
        const textArea = document.createElement('textarea');
        textArea.value = decodedText;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
      }
      
      const originalText = button.textContent;
      button.textContent = 'Copied!';
      button.classList.add('text-green-400');
      setTimeout(() => {
        button.textContent = originalText;
        button.classList.remove('text-green-400');
      }, 2000);
    } catch (error) {
      console.warn('Failed to copy', error);
      button.textContent = 'Failed';
      setTimeout(() => { button.textContent = 'Copy'; }, 2000);
    }
  };
}

// --- Exports ---

export async function markdownToHtml(content: string): Promise<string> {
  await loadHighlightTheme();
  // Reset counter for deterministic rendering if possible, though stateful renderers are tricky.
  // We'll let it increment to ensure unique IDs.
  
  return md.render(content);
}

export async function processMarkdownContent(container: HTMLElement) {
  const mermaidDivs = Array.from(container.querySelectorAll('.mermaid')) as HTMLElement[];
  if (mermaidDivs.length > 0) {
    try {
      await mermaid.run({ nodes: mermaidDivs });
    } catch (error) {
      console.error('Mermaid run failed', error);
    }
  }

  // Reset Album Counter for next render pass
  albumCounter = 0;
}