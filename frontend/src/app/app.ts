import { Component } from '@angular/core';

import { AskComponent } from './ask/ask.component';

@Component({
  selector: 'app-root',
  imports: [AskComponent],
  template: '<app-ask></app-ask>',
})
export class App {}
