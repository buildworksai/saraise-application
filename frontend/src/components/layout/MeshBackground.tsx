/**
 * Mesh Background Component
 * 
 * Animated gradient blobs with brand colors for glass panel background.
 */
export const MeshBackground = () => {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none -z-10">
      {/* Animated Gradient Blobs */}
      <div className="absolute top-0 -left-1/4 w-96 h-96 bg-deepBlue/20 blur-[120px] rounded-full animate-pulse-slow" />
      <div className="absolute top-1/4 right-0 w-80 h-80 bg-teal/20 blur-[100px] rounded-full animate-pulse-slow" style={{ animationDelay: '1s' }} />
      <div className="absolute bottom-0 left-1/3 w-96 h-96 bg-purple-500/10 blur-[120px] rounded-full animate-pulse-slow" style={{ animationDelay: '2s' }} />
      <div className="absolute bottom-1/4 right-1/4 w-72 h-72 bg-gold/10 blur-[80px] rounded-full animate-pulse-slow" style={{ animationDelay: '0.5s' }} />
      
      {/* Grid Overlay */}
      <div 
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage: 'radial-gradient(circle at 2px 2px, currentColor 1px, transparent 0)',
          backgroundSize: '40px 40px',
        }}
      />
    </div>
  );
};
