require('dotenv').config();
const express = require('express');
const axios = require('axios');
const path = require('path');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: false }));
app.use(express.static(path.join(__dirname, 'public')));

const TOKEN = process.env.SINRIC_TOKEN || '';
if (!TOKEN) {
  console.warn('Warning: SINRIC_TOKEN not set. Set it in .env or environment.');
}

app.post('/api/devices/:deviceId/action', async (req, res) => {
  const deviceId = req.params.deviceId;
  const { action, value, clientId } = req.body;

  if (!deviceId || !action) return res.status(400).json({ error: 'Missing deviceId or action' });

  const params = {
    clientId: clientId || 'web-app',
    type: 'request',
    createdAt: Date.now(),
    action,
    value: JSON.stringify(value || {})
  };

  const url = `https://api.sinric.pro/api/v1/devices/${encodeURIComponent(deviceId)}/action`;

  try {
    const response = await axios.get(url, {
      params,
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      timeout: 10000
    });

    res.status(response.status).send(response.data);
  } catch (err) {
    const status = err.response ? err.response.status : 500;
    const data = err.response ? err.response.data : { message: err.message };
    console.error('Sinric request error:', data);
    res.status(status).json({ error: data });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Server listening on ${PORT}`));
