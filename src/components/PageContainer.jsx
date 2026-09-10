const PageContainer = ({ children, title }) => {
  return (
    <div className="flex-1 p-8">
      {title && (
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">{title}</h1>
          <p className="text-gray-400">Manage your guest posting opportunities</p>
        </div>
      )}
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-6">
        {children}
      </div>
    </div>
  );
};

export default PageContainer;
