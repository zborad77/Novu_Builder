import React, { useState } from 'react';

function App() {
  const [text, setText] = useState('Click me!');

  const handleClick = () => {
    setText('Text has changed!');
  };

  return (
    <div>
      <h1>{text}</h1>
      <button onClick={handleClick}>Click me!</button>
    </div>
  );
}

export default App;