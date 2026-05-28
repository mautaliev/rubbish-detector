const imageInput = document.getElementById('imageInput');
const preview = document.getElementById('preview');
const placeholder = document.getElementById('placeholder');
const detectClass = document.getElementById('detectClass');
const checkButton = document.getElementById('checkButton');
const result = document.getElementById('result');

let selectedFile = null;

imageInput.addEventListener('change', () => {
  selectedFile = imageInput.files[0];
  result.innerHTML = '';

  if (!selectedFile) {
    preview.classList.add('hidden');
    placeholder.classList.remove('hidden');
    checkButton.disabled = true;
    return;
  }

  preview.src = URL.createObjectURL(selectedFile);
  preview.classList.remove('hidden');
  placeholder.classList.add('hidden');
  checkButton.disabled = false;
});

checkButton.addEventListener('click', async () => {
  if (!selectedFile) return;

  checkButton.disabled = true;
  result.innerHTML = 'Выполняется проверка изображения... Ожидание может занять до минуты.';

  const formData = new FormData();
  formData.append('file', selectedFile);
  formData.append('detect_class', detectClass.checked ? 'true' : 'false');
  formData.append('conf', '0.25');

  try {
    const response = await fetch('/api/detect-file', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Ошибка обработки изображения');
    }

    const data = await response.json();

    if (!data.image_base64 || !data.found || data.total === 0) {
      result.innerHTML = '<span class="success">Загрязнения не найдены.</span>';
      return;
    }

    preview.src = `data:image/jpeg;base64,${data.image_base64}`;
    result.innerHTML = renderFound(data);
  } catch (error) {
    result.innerHTML = `<span class="error">${error.message}</span>`;
  } finally {
    checkButton.disabled = false;
  }
});

function renderFound(data) {
  const items = Object.entries(data.found)
    .map(([name, value]) => `<li>${escapeHtml(name)}: ${value.count}</li>`)
    .join('');

  return `
    <div class="success">Обнаружено загрязнений: ${data.total}</div>
    <ul>${items}</ul>
  `;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
