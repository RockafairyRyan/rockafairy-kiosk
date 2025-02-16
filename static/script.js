//static/script.js
document.addEventListener('DOMContentLoaded', function() {
    // Gem animation (only if gems were earned)
    const gemAnimation = document.getElementById('gem-animation');
    if (gemAnimation) {
        const gems = gemAnimation.querySelectorAll('.gem');
        gems.forEach((gem, index) => {
            gem.style.animationDelay = `${index * 0.1}s`;
            const xPos = Math.random() * 80;
            const yPos = Math.random() * 80;
            gem.style.left = `${xPos}%`;
            gem.style.top = `${yPos}%`;
        });
    }

});