import { createApp } from 'vue';
import { createPinia } from 'pinia';
import { Quasar, Notify } from 'quasar';
import router from './router';
import App from './App.vue';

import '@quasar/extras/material-icons/material-icons.css';
import 'quasar/src/css/index.sass';
import './styles/app.scss';

const app = createApp(App);

app.use(createPinia());
app.use(router);
app.use(Quasar, {
  plugins: { Notify },
  config: {
    brand: {
      primary: '#0d4da1',
      secondary: '#0e2a47',
      accent: '#e9f3ff',
      dark: '#0d2e4d',
      positive: '#21BA45',
      negative: '#C10015',
      warning: '#F2C037',
      info: '#31CCEC',
    },
  },
});

app.mount('#app');
